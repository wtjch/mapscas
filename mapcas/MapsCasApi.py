from MapsGenericApi import *


class CasClient(MapsClient):
    """Client object to communicate with MAPS server
    
    The Client object stores all the required information to connect to the
    MAPS server as well as functions for making global config changes to the
    testbed and for starting and stopping scripts within the testbed.

    :param server_ip: IP Address of remote MAPS server.
    :param server_port: TCP Port of remote MAPS server, typically 10024.
    :param testbed: .xml testbed profile for server to use on init.
    """

    def __init__(self, server_ip, server_port, testbed="TestBedDefault.xml"):
        """Create a CasClient Object to communicate with remote server"""
        super(CasClient, self).__init__(server_ip, server_port, testbed)
        self.protocol = 'CAS'
        self.active_lines = {}

    def load_profile_group(self, profile_group="CAS_Profiles.xml"):
        """Loads a new .xml profile group into MAPS server testbed
        
        *Extends MapsClient.load_profile_group()*
        
        :param profile_group: name of .xml file to load (with .xml extension)
        :returns: 0 for success, >0 for failure
        """
        return super(CasClient, self).load_profile_group(profile_group)

    def open_line(self, line):
        """Initialize and reserve the analog line if line is not in use

        :param line: analog line number
        :type line: int
        :returns: CasCall object
        """
        cardno = self.get_card_from_line(line)
        ts = self.get_timeslot_from_line(line)

        script_name = "CLI_CAS.gls"
        profile = "Card1TS00"
        gc1 = "Cardno", "(i)" + str(cardno)
        gc2 = "TS", "(i)" + str(ts)
        gc_list = [gc1, gc2]

        handle = maps.StartScript(self.connection_id, script_name, profile, 1, gc_list)
        if handle != 0:
            status = maps.WaitForEvent(handle, "ScriptStatus", DEFAULT_TIME_OUT)
            if status == "Running":
                status = maps.WaitForEvent(handle, "TSStatus", DEFAULT_TIME_OUT)
                if status == "TS is unique":
                    tmp_call = CasCall(handle, maps, "LOW", "CAS")
                    self.active_lines[line] = tmp_call
                    return tmp_call
                else:
                    return CasCall(SERVER_ERROR_SCRIPT_IS_ALREADY_STARTED_ON_THE_SAME_SCRIPTID, None, None, None)
            else:
                return CasCall(CREATE_HANDLE_FAILURE, None, None, None)

    def close_line(self, call):
        """Close and release the line

        :param call: CasCall object
        :returns: 0 for success, error code otherwise
        """
        result = SUCCESS

        for k, v in self.active_lines.items():
            if v == call:
                del self.active_lines[k]

        if maps.StopScript(call.handle) != 0:
            status = maps.WaitForEvent(call.handle, "StopScriptStatus", DEFAULT_TIME_OUT)
            if status == "":
                result = SERVER_ERROR_TEST_BED_NOT_STARTED
            elif status != "Script Stopped":
                result = SERVER_ERROR_SCRIPT_NOT_AVAILABLE
        else:
            result = SENDING_FAILED

        self.response_code = result
        return result

    def get_cas_call(self, line):
        """Return the CasCall object based on the line number. CasCall
        object must be initialized by the open_line() function.
        
        :param line: analog line number
        :type line: int
        :returns: CasCall object if it exists, return None otherwise
        """
        if line in self.active_lines:
            return self.active_lines[line]
        else:
            return None

    @staticmethod
    def get_card_from_line(line):
        """Get T1 card number based on line number

        :param line: analog line number
        :type line: int
        :return: T1 card number
        """
        return (line - 1) / 24 + 1

    @staticmethod
    def get_timeslot_from_line(line):
        """Get T1 timeslot based on line number

        :param line (int) analog line number
        :returns: T1 timeslot
        """
        return (line - 1) % 24

    def system_check(self, t1_port):
        """
        Verify T1 system health. Check for dial tone on each timeslot of the specified T1 port

        :param t1_port: T1 port number
        :type t1_port: int
        :return: list ranging from 0-23 with the status of each T1 timeslot. Possible statuses are:
            "Port available", "Port in use", "No dial tone", "Hardware error"
        """
        t1_status = {}
        calls = {}
        for i in range(0, 23):
            t1_status[i] = "Port in use"

        start_port = (t1_port - 1) * 24 + 1
        end_port = start_port + 24

        # open 24 lines and start dial tone detection
        curr_port = start_port
        i = 0
        while curr_port < end_port:
            tmp_call = self.open_line(curr_port)
            if tmp_call.handle != 0:
                t1_status[i] = "Port available"
                calls[i] = tmp_call
            curr_port += 1
            i += 1

        # start detect dial tone
        curr_port = start_port
        i = 0
        gclist = list()
        while curr_port < end_port:
            if t1_status[i] == "Port available":
                tmp_call = self.get_cas_call(curr_port)
                maps.UserEvent(tmp_call.handle, "Verify Dial Tone", gclist)
            curr_port += 1
            i += 1

        # wait for result
        curr_port = start_port
        i = 0
        while curr_port < end_port:
            if t1_status[i] == "Port available":
                tmp_call = self.get_cas_call(curr_port)
                result = maps.WaitForEvent(tmp_call.handle, "VerifyDialTone", 10000)
                if result == "1":
                    t1_status[i] = "No dial tone"
                elif result == "2":
                    t1_status[i] = "Hardware error"
                self.close_line(tmp_call)
            curr_port += 1
            i += 1
        time.sleep(1)
        return t1_status


class CasCall(MapsCall):
    """Call object used to generate CAS(FXO) call and traffic.
    
    A CasCall object is associated with a script instance on the server on a
    one to one basis. The CasCall object is used to pass signaling and traffic
    instructions to the script on the server. An CasCall object represents ONE
    leg of a call, so if you want to control both legs you will need a
    CasCall object for each side of the call.

    *extends MapsCall()*
    
    :param handle: script ID provided by the server, should not be manipulated
        by user.
    :param status: call status, updated by various functions.
    :param level: [ HIGH | LOW ], indicates API level.
    :param call_type: [ PLACE_CALL | RECEIVE_CALL | BIND INCOMING CALL ].
    """
    return_code = ""
    rx_digits = ""
    vmwi_status = ""
    timeout_fax_default = 100000

    def __init__(self, handle, status, level, call_type):
        super(CasCall, self).__init__(handle, status, level, call_type)

    def answer_call(self):
        """Offhook to answer call.

        :returns: boolean
        """
        return self.offhook()

    def cas_event(self, event_name, var_list, timeout=20000):
        """Helper function to start userevent and get waitforevent result from CLI server

        :param event_name: user event name
        :param var_list: variables to pass to CLI server
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        return_variable = event_name.replace(" ", "")
        if maps.UserEvent(self.handle, event_name, var_list) != 0:
            self.return_code = maps.WaitForEvent(self.handle, return_variable, timeout + 5000)
            if self.return_code == "0":
                return True
        else:
            return False

    def offhook(self):
        """
        Offhook the line

        :returns: boolean
        """
        user_event = "Offhook"
        gclist = list()
        return self.cas_event(user_event, gclist, timeout_default)

    def onhook(self):
        """
        Onhook the line

        :returns: boolean
        """
        user_event = "Onhook"
        gclist = list()
        return self.cas_event(user_event, gclist, timeout_default)

    def place_call(self, num_to_dial="3015551234"):
        """
        Place call: go offhook, detect dial tone, and dial number

        :param num_to_dial: number to dial
        :type num_to_dial: string
        :returns: boolean
        """
        if self.offhook():
            if self.detect_dial_tone(20000):
                if self.dial(num_to_dial):
                    return True
        return False

    def cas_user_event_start(self, event_name, var_list):
        """helper function to start userevent

        :param event_name: user event name
        :param var_list: variables to pass to CLI server
        :returns: boolean
        """
        if maps.UserEvent(self.handle, event_name, var_list) != 0:
            return True
        else:
            return False

    def cas_wait_for_event(self, event_name, timeout=20000):
        """helper function to get waitforevent results

        :param event_name: user event name
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        return_variable = event_name.replace(" ", "")
        self.return_code = maps.WaitForEvent(self.handle, return_variable, timeout + 1000)
        if self.return_code == "0":
            return True
        else:
            return False

    def detect_busy_tone(self, timeout=20000, busy_tone_duration=10000):
        """Attempt to detect the busy tone on the line within the specified timeout period. Blocking function.

        Note: busy_tone_duration is considered if "set_tone_detection_type' is set to 1. Total busy tone duration on
        the line must be equal or greater than busy_tone_duration.

        :param timeout: timeout in msec
        :type timeout: int
        :param busy_tone_duration: expected total duration of busy tone in msec
        :type busy_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Busy Tone"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'BUSY_TONE_DURATION', "(i)" + str(busy_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_busy_tone_start(self, timeout=20000, busy_tone_duration=10000):
        """Start the busy tone detector on the line for the specified timeout period. Non-blocking function.

        Note: busy_tone_duration is considered if "set_tone_detection_type' is set to 1. Total busy tone duration on
        the line must be equal or greater than busy_tone_duration.

        :param timeout: timeout in msec
        :type timeout: int
        :param busy_tone_duration: expected total duration of busy tone in msec
        :type busy_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Busy Tone"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'BUSY_TONE_DURATION', "(i)" + str(busy_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_busy_tone_wait_for_result(self, timeout=20000):
        """Wait for busy tone result on the line within the specified timeout period. Blocking function.

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Busy Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_call_waiting_tone(self, timeout=20000):
        """Attempt to detect the call waiting tone on the line within the specified timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
            """
        user_event = "Detect Call Waiting Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def detect_call_waiting_tone_start(self, timeout=20000):
        """Start the call waiting tone detector for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Call Waiting Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_call_waiting_tone_wait_for_result(self, timeout=20000):
        """Wait for call waiting tone detector to return the results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Call Waiting Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_confirmation_tone(self, timeout=20000):
        """Attempt to detect the confirmation tone on the line within the specified timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Confirmation Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gc_list = [gc1]
        return self.cas_event(user_event, gc_list, timeout)

    def detect_confirmation_tone_start(self, timeout=20000):
        """Start the confirmation tone detector for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Confirmation Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_confirmation_tone_wait_for_result(self, timeout=20000):
        """Wait for confirmation tone detector to return the results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
            """
        user_event = "Detect Confirmation Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_dial_tone(self, timeout=20000, dial_tone_duration=20000):
        """Attempt to detect the dial tone on the line within the specified timeout period. Blocking function.

        Note: dial_tone_duration is taken into account if set_tone_detection_type() is set to 1, the dial tone must be
        present on the line for the specified duration. Any duration longer or shorter will result in a failure.

        :param timeout: timeout in msec
        :type timeout: int
        :param dial_tone_duration: expected duration (in msec) of dial tone
        :type dial_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Dial Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gc2 = "DIAL_TONE_DURATION", "(i)" + str(dial_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_dial_tone_start(self, timeout=20000, dial_tone_duration=20000):
        """Start the dial tone detector for detection within the timeout period. Non-blocking function

        Note: dial_tone_duration is taken into account if set_tone_detection_type() is set to 1, the dial tone must be
        present on the line for the specified duration. Any duration longer or shorter will result in a failure.

        :param timeout: timeout in msec
        :type timeout: int
        :param dial_tone_duration: expected duration (in msec) of dial tone
        :type dial_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Dial Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gc2 = "DIALTONE_DURATION", "(i)" + str(dial_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_dial_tone_wait_for_result(self, timeout=20000):
        """Wait for dial tone detector to return the results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Dial Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_distinctive_ringing_signal(self, ring_count, ring_on_1, ring_off_1, ring_on_2,
                                          ring_off_2, ring_on_3, ring_off_3, ring_on_4, ring_off_4, timeout=20000):
        """Attempt to detect the user-defined distinctive ringing signal on the line
        within the specified timeout period. Blocking function

        :param ring_count: number of rings to detect in msec
        :type ring_count: int
        :param ring_on_1: 1st ring on duration in msec
        :type ring_on_1: float
        :param ring_off_1: 1st ring off duration in msec
        :type ring_off_1: float
        :param ring_on_2: 2nd ring on duration in msec
        :type ring_on_2: float
        :param ring_off_2: 2nd ring off duration in msec
        :type ring_off_2: float
        :param ring_on_3: 3rd ring on duration in msec
        :type ring_on_3: float
        :param ring_off_3: 3rd ring off duration in msec
        :type ring_off_3: float
        :param ring_on_4: 4th ring on duration in msec
        :type ring_on_4: float
        :param ring_off_4: 4th ring off duration in msec
        :type ring_off_4: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Distinctive Ringing Signal"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_COUNT', "(i)" + str(ring_count)
        gc3 = 'RON1', "(f)" + str(ring_on_1)
        gc4 = 'ROFF1', "(f)" + str(ring_off_1)
        gc5 = 'RON2', "(f)" + str(ring_on_2)
        gc6 = 'ROFF2', "(f)" + str(ring_off_2)
        gc7 = 'RON3', "(f)" + str(ring_on_3)
        gc8 = 'ROFF3', "(f)" + str(ring_off_3)
        gc9 = 'RON4', "(f)" + str(ring_on_4)
        gc10 = 'ROFF4', "(f)" + str(ring_off_4)
        gclist = [gc1, gc2, gc3, gc4, gc5, gc6, gc7, gc8, gc9, gc10]
        return self.cas_event(user_event, gclist, timeout)

    def detect_distinctive_ringing_signal_start(self, ring_count, ring_on_1, ring_off_1, ring_on_2,
                                                ring_off_2, ring_on_3, ring_off_3, ring_on_4, ring_off_4,
                                                timeout=20000):
        """Start the distinctive ringing signal detector on the line for detection
        within the specified timeout period. Non-blocking function

        :param ring_count: number of rings to detect in msec
        :type ring_count: int
        :param ring_on_1: 1st ring on duration in msec
        :type ring_on_1: float
        :param ring_off_1: 1st ring off duration in msec
        :type ring_off_1: float
        :param ring_on_2: 2nd ring on duration in msec
        :type ring_on_2: float
        :param ring_off_2: 2nd ring off duration in msec
        :type ring_off_2: float
        :param ring_on_3: 3rd ring on duration in msec
        :type ring_on_3: float
        :param ring_off_3: 3rd ring off duration in msec
        :type ring_off_3: float
        :param ring_on_4: 4th ring on duration in msec
        :type ring_on_4: float
        :param ring_off_4: 4th ring off duration in msec
        :type ring_off_4: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Distinctive Ringing Signal"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_COUNT', "(i)" + str(ring_count)
        gc3 = 'RON1', "(f)" + str(ring_on_1)
        gc4 = 'ROFF1', "(f)" + str(ring_off_1)
        gc5 = 'RON2', "(f)" + str(ring_on_2)
        gc6 = 'ROFF2', "(f)" + str(ring_off_2)
        gc7 = 'RON3', "(f)" + str(ring_on_3)
        gc8 = 'ROFF3', "(f)" + str(ring_off_3)
        gc9 = 'RON4', "(f)" + str(ring_on_4)
        gc10 = 'ROFF4', "(f)" + str(ring_off_4)
        gclist = [gc1, gc2, gc3, gc4, gc5, gc6, gc7, gc8, gc9, gc10]
        return self.cas_user_event_start(user_event, gclist)

    def detect_distinctive_ringing_signal_wait_for_result(self, timeout=20000):
        """Wait for distinctive ringing signal detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Distinctive Ringing Signal"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_howler_tone(self, timeout=20000):
        """Attempt to detect the howler tone on the line within the timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Howler Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def detect_howler_tone_start(self, timeout=20000):
        """Start the howler tone detector on the line for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Howler Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_howler_tone_wait_for_result(self, timeout=20000):
        """Wait for howler tone detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Howler Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_reorder_tone(self, timeout=20000, reorder_tone_duration=10000):
        """Attempt to detect the reorder tone on the line within the timeout period. Blocking function

        Note: reorder_tone_duration is considered if set_tone_detection_type is set to 1. Total reorder tone duration
        on the line must be equal to or greater reorder_tone_duration.

        :param timeout: timeout in msec
        :type timeout: int
        :param reorder_tone_duration: total reorder tone duration in msec
        :type reorder_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Reorder Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gc2 = "REORDER_TONE_DURATION", "(i)" + str(reorder_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_reorder_tone_start(self, timeout=20000, reorder_tone_duration=10000):
        """Start the reorder tone detector on the line for detection within the timeout period. Non-blocking function

        Note: reorder_tone_duration is considered if set_tone_detection_type is set to 1. Total reorder tone duration
        on the line must be equal to or greater reorder_tone_duration.

        :param timeout: timeout in msec
        :type timeout: int
        :param reorder_tone_duration: total reorder tone duration in msec
        :type reorder_tone_duration: int
        :returns: boolean
        """
        user_event = "Detect Reorder Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gc2 = "REORDER_TONE_DURATION", "(i)" + str(reorder_tone_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_reorder_tone_wait_for_result(self, timeout=20000):
        """Wait for the reorder tone detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Reorder Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_ringback_tone(self, timeout=20000):
        """Attempt to detect the ringback tone on the line within the timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringback Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def detect_ringback_tone_start(self, timeout=20000):
        """Start the ringback tone detector on the line for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringback Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_ringback_tone_wait_for_result(self, timeout=20000):
        """Wait for ringback tone to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringback Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_ringing_signal(self, ring_count=1, ring_on=2000.00, ring_off=4000.00, timeout=20000):
        """Attempt to detect the ringing signal on the line within the specified timeout period. Blocking function

        :param ring_count: number of ring cycles to detect. ring cycle is defined as the ring-on plus ring-off duration
        :type ring_count: int
        :param ring_on: ring on duration in msec
        :type ring_on: float
        :param ring_off: ring off duration in msec
        :type ring_off: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringing Signal"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_COUNT', "(i)" + str(ring_count)
        gc3 = 'RING_ON', "(f)" + str(ring_on)
        gc4 = 'RING_OFF', "(f)" + str(ring_off)
        gclist = [gc1, gc2, gc3, gc4]
        return self.cas_event(user_event, gclist, timeout)

    def detect_ringing_signal_start(self, ring_count=1, ring_on=2000.00, ring_off=4000.00, timeout=20000):
        """Start the ringing signal detector on the line for detection within the specified timeout period.
        Non-blocking function

        :param ring_count: number of ring cycles to detect. ring cycle is defined as the ring-on plus ring-off duration
        :type ring_count: int
        :param ring_on: ring on duration in msec
        :type ring_on: float
        :param ring_off: ring off duration in msec
        :type ring_off: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringing Signal"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_COUNT', "(i)" + str(ring_count)
        gc3 = 'RING_ON', "(f)" + str(ring_on)
        gc4 = 'RING_OFF', "(f)" + str(ring_off)
        gclist = [gc1, gc2, gc3, gc4]
        return self.cas_user_event_start(user_event, gclist)

    def detect_ringing_signal_wait_for_result(self, timeout=20000):
        """Wait for ringing signal detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ringing Signal"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_ring_splash(self, ring_splash_duration, timeout=20000):
        """Attempt to detect ring splash on the line within the specified timeout period. Blocking function

        :param ring_splash_duration: ring splash duration in msec
        :type ring_splash_duration: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ring Splash"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_SPLASH_DURATION', "(f)" + str(ring_splash_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_ring_splash_start(self, ring_splash_duration, timeout=20000):
        """Start the ring splash detector on the line for detection within the specified timeout period.
        Non-blocking function

        :param ring_splash_duration: ring splash duration in msec
        :type ring_splash_duration: float
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ring Splash"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'RING_SPLASH_DURATION', "(f)" + str(ring_splash_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_ring_splash_wait_for_result(self, timeout=20000):
        """Wait for ring splash detector to return results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Ring Splash"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_silence(self, silence_duration, timeout=20000):
        """Attempt to detect the specified amount of silence within the timeout period. Blocking function

        :param silence_duration: silence duration in msec
        :type silence_duration: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Silence"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'SILENCE_DURATION', "(i)" + str(silence_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_silence_start(self, silence_duration, timeout=20000):
        """Start the silence detector on the line for detection of the specified amount of silence within the timeout
        period. Non-blocking function

        :param silence_duration: silence duration in msec
        :type silence_duration: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Silence"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'SILENCE_DURATION', "(i)" + str(silence_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_silence_wait_for_result(self, timeout=20000):
        """Wait for silence detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Silence"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_special_dial_tone(self, timeout=20000):
        """Attempt to detect the special dial tone on the line within the specified timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Special Dial Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def detect_special_dial_tone_start(self, timeout=20000):
        """Start the special dial tone detector for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Special Dial Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_special_dial_tone_wait_for_result(self, timeout=20000):
        """Wait for special dial tone detector to return the results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Special Dial Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_speech(self, speech_duration, timeout=20000):
        """Attempt to detect the specified amount of speech within the timeout period. Blocking function

        :param speech_duration: silence duration in msec
        :type speech_duration: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Verify Speech"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'SPEECH_DURATION', "(i)" + str(speech_duration)
        gclist = [gc1, gc2]
        return self.cas_event(user_event, gclist, timeout)

    def detect_speech_start(self, speech_duration, timeout=20000):
        """Start the speech detector on the line to detect the specified amount of speech within the timeout period.
        Non-blocking function

        :param speech_duration: silence duration in msec
        :type speech_duration: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Verify Speech"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'SPEECH_DURATION', "(i)" + str(speech_duration)
        gclist = [gc1, gc2]
        return self.cas_user_event_start(user_event, gclist)

    def detect_speech_wait_for_result(self, timeout=20000):
        """Wait for speech detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Verify Speech"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_test_tone(self, timeout=20000):
        """Attempt to detect the 1004 Hz test tone on the line within the specified timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Test Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def detect_test_tone_start(self, timeout=20000):
        """Start the testone detector to detect the 1004 Hz test tone on the line within the specified timeout period.
        Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Test Tone"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_test_tone_wait_for_result(self, timeout=20000):
        """Wait for test tone detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Test Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_tone(self, freq1, freq2, timeout=20000):
        """Attempt to detect the user-defined tone on the line within the specified timeout period. Blocking function

        :param freq1: first frequency
        :type freq1: int
        :param freq2: second frequency (set to 0 for single frequency tone)
        :type freq2: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Tone"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'FREQ1', "(i)" + str(freq1)
        gc3 = 'FREQ2', "(i)" + str(freq2)
        gclist = [gc1, gc2, gc3]
        return self.cas_event(user_event, gclist, timeout)

    def detect_tone_start(self, freq1, freq2, timeout=20000):
        """Start the tone detector to detect the user-defined tone on the line within the specified timeout period.
        Non-blocking function

        :param freq1: first frequency
        :type freq1: int
        :param freq2: second frequency (set to 0 for single frequency tone)
        :type freq2: int
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Tone"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'FREQ1', "(i)" + str(freq1)
        gc3 = 'FREQ2', "(i)" + str(freq2)
        gclist = [gc1, gc2, gc3]
        return self.cas_user_event_start(user_event, gclist)

    def detect_tone_wait_for_result(self, timeout=20000):
        """Wait for tone detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect Tone"
        return self.cas_wait_for_event(user_event, timeout)

    def detect_vmwi(self, timeout=20000):
        """Attempt to detect the visual message waiting indicator on the line within the specified timeout period.
        Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Detect VMWI"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        if self.cas_event(user_event, gclist, timeout):
            result = maps.WaitForEvent(self.handle, "VMWIStatus", timeout)
            if result == "0":
                self.vmwi_status = "On"
            elif result == "1":
                self.vmwi_status = "Off"
            return True
        self.vmwi_status = "Not Available"
        return False

    def detect_vmwi_start(self, timeout=20000):
        """Start the VMWI detector for detection within the timeout period. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :return:
        """
        user_event = "Detect VMWI"
        gc1 = "TIMEOUT", "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_vmwi_wait_for_result(self, timeout=20000):
        """Wait for VMWI detector to return the results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :return:
        """
        user_event = "Detect VMWI"
        if self.cas_wait_for_event(user_event, timeout=20000):
            result = maps.WaitForEvent(self.handle, "VMWIStatus", timeout)
            if result == 0:
                self.vmwi_status = "On"
            else:
                self.vmwi_status = "Off"
            return True
        self.vmwi_status = "Not Available"
        return False

    def dial(self, digits):
        """Dial the specified DTMF digits on the line

        :param digits: DTMF digits to dial
        :type digits: string
        :returns: boolean
        """
        user_event = "Dial"
        gc1 = "DIGITS", "(s)" + digits
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout_default)

    def flash(self):
        """Hook flash the line

        :returns: boolean
        """
        user_event = "Flash"
        gclist = list()
        return self.cas_event(user_event, gclist, timeout_default)

    def get_error_message(self):
        """
        :return: String explanation of error code
        """
        if self.return_code == "0":
            return "None"
        elif self.return_code == "1":
            return "Timeout"
        elif self.return_code == "2":
            return "Line is onhook"
        elif self.return_code == "3":
            return "Line is offhook"
        elif self.return_code == "10":
            return "Digit: Invalid type"
        elif self.return_code == "20":
            return "Region is undefined"
        elif self.return_code == "30":
            return "Fax: Out of rates"
        elif self.return_code == "31":
            return "Fax: Invalid data rate"
        elif self.return_code == "32":
            return "Fax: Frame check error"
        elif self.return_code == "33":
            return "Fax: Failure"
        elif self.return_code == "34":
            return "Fax: Another session active"
        elif self.return_code == "35":
            return "Fax: T1 timeout"
        elif self.return_code == "36":
            return "Fax: Cannot open TIFF file"
        elif self.return_code == "37":
            return "Fax: TIFF file name missing"
        else:
            return "Error %s" % self.return_code

    def get_vmwi(self):
        """Return VMWI status

        :return: "On" or "Off"
        """
        return self.vmwi_status

    def set_tone_detection_type(self, tone_type):
        """ Set tone detection mode and margin of error

        Tone type 0: Detect tone presence only.
        Tone type 1: Verify tone is present for specified duration (Implemented for dial tone, busy tone,
        and re-order tone).

        :param tone_type: 0 or 1
        :type tone_type: int
        :return: boolean
        """
        user_event = "Set Tone Detection"
        gc1 = 'TONE_TYPE', "(i)" + str(tone_type)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout_default)

    def set_fax(self, codec="MULAW", min_data_rate=4800, max_data_rate=12000, ecm_enable=1):
        """Configure fax parameters

        :param codec: specify "MULAW" or "ALAW"
        :type codec: string
        :param min_data_rate: select 2400, 4800, 7200, 9600, 12000, 14400, 16800, 33600
        :type min_data_rate: int
        :param max_data_rate: select 2400, 4800, 7200, 9600, 12000, 14400, 16800, 33600
        :type max_data_rate: int
        :param ecm_enable: 0 to disable, 1 to enable
        :type ecm_enable: int
        :returns: boolean
        """
        user_event = "Set Fax"
        gc1 = 'FAX_MIN_DATA_RATE', "(i)" + str(min_data_rate)
        gc2 = 'FAX_MAX_DATA_RATE', "(i)" + str(max_data_rate)
        gc3 = 'FAX_CODEC_TYPE', "(s)" + codec
        gc4 = 'FAX_ECMENABLED', "(i)" + str(ecm_enable)
        gclist = [gc1, gc2, gc3, gc4]
        return self.cas_event(user_event, gclist, timeout_default)

    def set_region(self, region):
        """Select the current region

        :param region: available regions are defined in the "Regions.xml" profile on the CAS server
        :type region: string
        :returns: boolean
        """
        user_event = "Set Region"
        gc1 = 'REGION', "(s)" + region
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout_default)

    def tdm_get_received_digits(self):
        """ Return the last detected digits
        """
        return self.rx_digits

    def tdm_receive_digits_start(self, timeout=20000):
        """Start the digit detector. Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        event_name = "Detect Digits"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gc2 = 'DIGIT_TYPE', "(s)" + 'dtmf'
        gclist = [gc1, gc2]
        return self.cas_user_event_start(event_name, gclist)

    def tdm_receive_digits_wait_for_detection(self, timeout=20000):
        """Wait for digit detector results. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        event_name = "Detect Digits"
        if self.cas_wait_for_event(event_name, timeout):
            self.rx_digits = maps.WaitForEvent(self.handle, "DetectedDigits", 2000)
            return True
        return False

    def tdm_receive_fax_start(self, fax_path, timeout=timeout_fax_default):
        """Start fax reception to the specified path. Fax files have .tif extension. Non-blocking function

        :param fax_path: file path for received fax file
        :type fax_path: string
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Receive Fax"
        gc1 = 'RX_FAX_PATH', "(s)" + fax_path
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def tdm_receive_fax_wait_for_completion(self, timeout=timeout_fax_default):
        """Receive fax to the specified path. Fax files have .tif extension. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "FaxReceived"
        return self.cas_wait_for_event(user_event, timeout)

    def tdm_receive_file_start(self, rx_filename, rx_file_duration):
        """Start file reception. Non-blocking function

        :param rx_filename: file path and name
        :type rx_filename: string
        :param rx_file_duration: receive duration in msec
        :type rx_file_duration: integer
        :returns: boolean
        """
        event_name = "Receive File"
        gc1 = 'FILE_DURATION', "(i)" + str(rx_file_duration)
        gc2 = 'RX_PATH', "(s)" + rx_filename
        gclist = [gc1, gc2]
        return self.cas_event(event_name, gclist, rx_file_duration)

    def tdm_receive_file_stop(self):
        """Stop file reception on the line

        :returns: boolean
        """
        user_event = "Stop Receive File"
        gclist = list()
        return self.cas_event(user_event, gclist, timeout_default)

    def tdm_receive_file_voice_activated_start(self, rx_filename, wait_for_voice_timeout,
                                               end_of_voice_silence_duration, minimum_receive_duration):
        """Voice activated receive file. Start recording file after detecting voice
        activity. Recording stops after "end_of_voice_silence_duration" is detected.
        Maximum record duration is 10 minutes. This is a non-blocking function.

        :param rx_filename: receive file path and name
        :type rx_filename: string
        :param wait_for_voice_timeout: timeout period in msec to wait for speech to appear on the line
        :type wait_for_voice_timeout: int
        :param end_of_voice_silence_duration: end of voice silence duration in msec
        :type end_of_voice_silence_duration: int
        :param minimum_receive_duration: minimum receive file duration in msec. The minimum duration must be satisfied
            before detecting end of voice silence
        :type minimum_receive_duration: int
        :returns: boolean
        """
        event_name = "Receive File Voice Activated"
        gc1 = 'TIMEOUT', "(i)" + str(wait_for_voice_timeout)
        gc2 = 'SILENCE_DURATION', "(i)" + str(end_of_voice_silence_duration)
        gc3 = 'MINIMUM_RECEIVE_DURATION', "(i)" + str(minimum_receive_duration)
        gc4 = 'RX_PATH', "(s)" + rx_filename
        gclist = [gc1, gc2, gc3, gc4]
        return self.cas_user_event_start(event_name, gclist)

    def tdm_receive_file_voice_activated_wait_for_completion(self, timeout=20000):
        """Wait for voice activated receive file to complete

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "ReceiveFileVoiceActivated"
        return self.cas_wait_for_event(user_event, timeout)

    def tdm_receive_file_wait_for_completion(self, timeout=20000):
        """Wait for file reception to complete

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        event_name = "File Received"
        return self.cas_wait_for_event(event_name, timeout)

    def tdm_send_digits(self, digit_type='dtmf', digits='12345', power='-10.00', on_time=80, off_time=80):
        """Send digits

        :param digit_type: "dtmf" or "mf"
        :type digit_type: string
        :param digits: digits to send
        :type digits: string
        :param power: digit power in dBm (default = "-13.00")
        :type power: string
        :param on_time: on duration in msec
        :type on_time: int
        :param off_time: off duration in msec
        :type off_time: int
        :returns: boolean
        """
        user_event = "Send Digits"
        gc1 = 'DIGIT_ON', "(i)" + str(on_time)
        gc2 = 'DIGIT_OFF', "(i)" + str(off_time)
        gc3 = 'DIGITS', "(s)" + digits
        gc4 = 'DIGIT_POWER', "(s)" + power
        gc5 = 'DIGIT_TYPE', "(s)" + digit_type
        gclist = [gc1, gc2, gc3, gc4, gc5]
        return self.cas_event(user_event, gclist, timeout_default)

    def tdm_send_fax_start(self, fax_path, timeout=timeout_fax_default):
        """Send fax file on the line

        :param fax_path: path of fax file to transmit(.TIF)
        :type fax_path: string
        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "Send Fax"
        gc1 = 'TX_FAX_PATH', "(s)" + fax_path
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout)

    def tdm_send_fax_wait_for_completion(self, timeout=timeout_fax_default):
        """Wait for send fax to complete. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        user_event = "FaxSent"
        return self.cas_wait_for_event(user_event, timeout)

    def tdm_send_file_start(self, filename, duration):
        """Start file transmission. Non-blocking function

        :param filename: path of audio file (.pcm)
        :type filename: string
        :param duration: file duration in msec (set to 0 to send file in entirety
        :type duration: int
        :returns: boolean
        """
        event_name = "Send File"
        gc1 = 'FILE_DURATION', "(i)" + str(duration)
        gc2 = 'TX_PATH', "(s)" + filename
        gclist = [gc1, gc2]
        return self.cas_event(event_name, gclist, duration)

    def tdm_send_file_stop(self):
        """Stop file transmission on the line

        :returns: boolean
        """
        user_event = "Stop Send File"
        gclist = list()
        return self.cas_event(user_event, gclist, timeout_default)

    def tdm_send_file_wait_for_completion(self, timeout=20000):
        """Wait for file transmission to complete. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: boolean
        """
        event_name = "File Sent"
        return self.cas_wait_for_event(event_name, timeout)

    def tdm_send_test_tone(self, duration=3000):
        """Send 1004 Hz test one on the line with the specified duration. Non-blocking function

        :param duration: tone duration in msec
        :type duration: int
        :returns: boolean
        """
        user_event = "Send Test Tone"
        gc1 = 'TONE_DURATION', "(i)" + str(duration)
        gclist = [gc1]
        return self.cas_event(user_event, gclist, timeout_default)

    def tdm_send_tone(self, freq1=1004, freq2=0, duration=3000):
        """Send user defined tone on the line with the specified duration

        :param freq1: first frequency in Hz
        :type freq1: int
        :param freq2: second frequency in Hz. Set to 0 to send single-frequency tone
        :type freq2: int
        :param duration: tone duration in msec
        :type duration: int
        :returns: boolean
        """
        user_event = "Send Tone"
        gc1 = 'TONE_DURATION', "(i)" + str(duration)
        gc2 = 'FREQ1', "(i)" + str(freq1)
        gc3 = 'FREQ2', "(i)" + str(freq2)
        gclist = [gc1, gc2, gc3]
        return self.cas_event(user_event, gclist, duration + timeout_default)

    def detect_caller_id(self, timeout=20000):
        """Attempt to detect caller ID on the line within the specified timeout period. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: CallerId
        """
        user_event = "Detect Caller ID"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gclist = [gc1]
        if self.cas_event(user_event, gclist, timeout):
            tmp_name = maps.WaitForEvent(self.handle, "CIDName", timeout)
            tmp_number = maps.WaitForEvent(self.handle, "CIDNumber", timeout)
            tmp_date = maps.WaitForEvent(self.handle, "CIDDate", timeout)
            tmp_time = maps.WaitForEvent(self.handle, "CIDTime", timeout)
            return CallerId(tmp_name, tmp_number, tmp_date, tmp_time)
        else:
            return CallerId()

    def detect_caller_id_start(self, timeout=20000):
        """Start the caller ID detector to detect caller ID on the line within the specified timeout period.
        Non-blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: CallerId
        """
        user_event = "Detect Caller ID"
        gc1 = 'TIMEOUT', "(i)" + str(timeout)
        gclist = [gc1]
        return self.cas_user_event_start(user_event, gclist)

    def detect_caller_id_wait_for_result(self, timeout=20000):
        """Wait for caller id detector to return result. Blocking function

        :param timeout: timeout in msec
        :type timeout: int
        :returns: CallerId
        """
        user_event = "Detect Caller ID"
        if self.cas_wait_for_event(user_event, timeout):
            tmp_name = maps.WaitForEvent(self.handle, "CIDName", timeout)
            tmp_number = maps.WaitForEvent(self.handle, "CIDNumber", timeout)
            tmp_date = maps.WaitForEvent(self.handle, "CIDDate", timeout)
            tmp_time = maps.WaitForEvent(self.handle, "CIDTime", timeout)
            return CallerId(tmp_name, tmp_number, tmp_date, tmp_time)
        else:
            return CallerId()


class CallerId(object):
    def __init__(self, *arg):
        if len(arg) == 0:
            self.name = ""
            self.number = ""
            self.date = ""
            self.time = ""
        else:
            self.name = arg[0]
            self.number = arg[1]
            self.date = arg[2]
            self.time = arg[3]
            super(CallerId, self).__init__()


timeout_default = 20000
