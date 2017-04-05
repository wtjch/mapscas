import PythonMapsCliIfc as maps
import time


class MapsClient(object):
    def __init__(self, server_ip, server_port, testbed):
        """Client object to communicate with MAPS server

        The Client object stores all the required information to connect to the
        MAPS server as well as functions for making global config changes to the
        testbed and for starting and stopping scripts within the testbed.

        :param server_ip: IP Address of remote MAPS server.
        :param server_port: TCP Port of remote MAPS server, typically 10024.
        :param testbed: .xml testbed profile for server to use on init.
        :var protocol: Protocol of MAPS server, ie SIP, ISDN etc.
        :var status: Status of MAPS server.
        """
        self.server_ip = server_ip
        self.server_port = server_port
        self.protocol = 'NONE'
        self.status = ''
        self.testbed = testbed
        script_list = []
        connection_id = 0
        self.response_code = UNKNOWN_RESPONSE_CODE


    # def __repr(self):

    def __str__(self):
        return '%s:%s\nProtocol=%s\nTestbed=%s\nStatus=%s' % (
            self.server_ip, self.server_port, self.protocol,
            self.testbed, self.status )
    
    def connect(self):
        """Attempt to open TCP session with MAPS server.

        :returns: 0 if success, >0 if failure
        """
        result = CONNECT_FAILED
        self.connection_id = maps.Connect(0, self.server_ip, self.server_port)
        if self.connection_id != 0:
            self.status = "CONNECTED"
            result = SUCCESS
        return result
        
    def disconnect(self):
        """Close TCP session with MAPS server.

        :returns: 0 if success, >0 if failure
        """
        result = DISCONNECT_FAILED
        if maps.Disconnect(self.connection_id) != 0:
            self.status = "DISCONNECTED"
            result = SUCCESS
        return result
        
    def start_testbed(self):
        """Initialize MAPS server to generate/receive traffic.

        Must be run before any calls can be created.

        :returns: 0 if success, >0 if failure
        """
        
        GCList = list()
        if maps.StartTestBedSetUp(self.connection_id, self.testbed, GCList) != 0:
            start_status = maps.WaitForEvent(self.connection_id, "StartStatus", 10000, 0)
            if start_status == "Started":
                result = SUCCESS
                self.status = "STARTED"
            elif start_status == "Maps init script not found":
                result = SERVER_ERROR_MAPS_INIT_SCRIPT_NOT_FOUND
            else:
                result = SERVER_ERROR_PARSING_ERROR_IN_THE_MAPS_INIT_SCRIPT
                # print "Parsing error line number = " + str(get_line_number(start_status))
        else:
            result = SENDING_FAILED        
        return result
        
    def load_profile_group(self, profile_group):
        """Loads a new .xml profile group into MAPS server testbed

        :param profile_group: name of .xml file to load (with .xml extension)
        :returns: 0 for success, >0 for failure
        """
        result = SUCCESS
        if maps.LoadProfile(self.connection_id, profile_group) != 0:
            status = maps.WaitForEvent(self.connection_id, "LoadProfileStatus", DEFAULT_TIME_OUT, 0)
            if status == "":
                result = SERVER_ERROR_TEST_BED_NOT_STARTED
            elif status != "Profile Loaded":
                result = PROFILE_LOADING_FAILURE
        else:
            result = SENDING_FAILED   
        return result
        
    def set_global_variable(self, variable_name, variable_type, variable_value):
        """Set global variables for server testbed.

        Global variables that will be accessible to all scripts run by this server.

        :param variable_name: name of variable, must be proceeded by '_'
        :param variable_type: [ '(i)' | '(s)' | '(f)' ] for int | string | float
        :param variable_value: the value this variable should store
        :returns: 0 for success, >0 for failure
        """
        result = SUCCESS
        function_arg = variable_name, variable_type + variable_value
        arg = [function_arg]
        if maps.ApplyGlobalEvent(self.connection_id, arg) == 0:
            result = SENDING_FAILED
        return result
    
    def start_call_script(self, level, call_type, profile):
        """Must be overridden by subclasses"""
        raise NotImplementedError
    
    def stop_call_script(self, call):
        """Must be overridden by subclasses"""
        raise NotImplementedError
        
    def stop_testbed(self):
        """Stop MAPS server testbed.

        Once testbed is stopped, MAPS will no longer to be able to generate
        or receive traffic of any kind. All currently active sessions will be
        stopped.

        :returns: 0 if success, >0 if failure
        """
        if maps.StopTestBedSetUp(self.connection_id) != 0:
            status = maps.WaitForEvent(self.connection_id, "StopStatus", DEFAULT_TIME_OUT, 0)
            if status == "Stopped":
                result = SUCCESS
            elif status == "MapsShutdown script is not exist":
                result = SERVER_ERROR_MAPS_SHUT_DOWN_SCRIPT_NOT_FOUND
            else:
                result = SERVER_ERROR_PARSING_ERROR_IN_THE_MAPS_SHUT_DOWN_SCRIPT
        else:
            result = SENDING_FAILED
        return result

class MapsCall(object):
    """Generic call object.

    A MapsCall object is associated with a script instance on the server on a
    one to one basis. It represents a single leg of a call.

    **Must be extended by subclass**

    :param handle: script ID to be provided by server.
    :param status: Status of call.
    :param level: [ 'HIGH' | 'LOW' ]
    :param call_type: determines what script to start at server.
    """
    def __init__(self, handle, status, level, call_type):
        self.handle = handle
        self.status = status
        self.level = level
        self.type = call_type
        self.message_list = []
        self.response_code = UNKNOWN_RESPONSE_CODE
        
    def set_local_variable(self, variable_name, variable_value):
        """Set the value of a local variable in server side script.

        :param variable_name: Name of variable to set.
        :param variable_type: [ '(i)' | '(s)' | '(f)' ] for
            int | string | float
        :param variable_value: Value to be stored by variable in script.
        :returns: 0 if success, 0> if failure
        """
        if type(variable_value) == type(int()):
            variable_type = "(i)"
            function_arg = variable_name, variable_type + `variable_value`
        elif type(variable_value) == type(str()):
            variable_type = "(s)"
            function_arg = variable_name, variable_type + variable_value
        elif type(variable_value) == type(float()):
            variable_type = "(f)"
            function_arg = variable_name, variable_type + variable_value
            
        result = SUCCESS
        arg = [function_arg]
        if maps.UserEvent(self.handle, "SetVariable", arg) != 0:
            status = maps.WaitForEvent(self.handle, "UserEventStatus", DEFAULT_TIME_OUT)
            if status == "":
                result = SERVER_ERROR_TEST_BED_NOT_STARTED
            elif status != "Applied":
                result = SERVER_ERROR_SCRIPT_NOT_AVAILABLE
        else:
            result = SENDING_FAILED
        return result
                
    def get_variable(self, variable_name):
        """Get the value of a variable from the server-side script.

        :param variable_name: Name of variable to get
        :returns: value stored in variable
        """
        GC1 = 'Var1', "(s)" + variable_name
        GCList = [GC1]
        response = ""
        result = SUCCESS
        if maps.UserEvent(self.handle, "GetVariable", GCList) != 0:
            status = maps.WaitForEvent(self.handle, "UserEventStatus", DEFAULT_TIME_OUT)
            if status == "":
                result = SERVER_ERROR_TEST_BED_NOT_STARTED
            elif status != "Applied":
                result = SERVER_ERROR_SCRIPT_NOT_AVAILABLE
            else:
                response = maps.WaitForEvent(self.handle, variable_name, 5000)
                if response == "":
                    result = UNKNOWN_VARIABLE
        else:
            result = SENDING_FAILED
        self.status = response
        self.response_code = result
        return response
        
    def wait_for_call_connect(self, time_out):
        # todo.doc
        """

        :param time_out:
        :returns:
        """
        time_out /= 1000
        response = ""
        result = SUCCESS
        while time_out > 0:
            response = get_call_status(handle)
            if response == "Connected":
                time_out = 0
            else:
                time_out -= 1
        if response != "Connected":
            result = WAIT_FOR_CALL_CONNECT_FAILURE
        self.status = response
        self.response_code = result
        return response
    
    def place_call(self):
        """Must be overridden by subclass"""
        raise NotImplementedError

        
DEFAULT_TIME_OUT = 3000
        
SUCCESS = 0
CONNECT_FAILED = 100
DISCONNECT_FAILED = 101
SENDING_FAILED = 102
START_TESTBED_FAILURE = 103
STOP_TESTBED_FAILURE = 104
PROFILE_LOADING_FAILURE = 105
CALL_STATUS_FAILURE = 106
TRANSPORT_FAILURE = 107
CREATE_HANDLE_FAILURE = 108
CALL_NOT_INITIATED = 109
ANSWER_CALL_FAILURE = 110
REJECT_CALL_FAILURE = 111
TERMINATE_CALL_FAILURE = 112
BINDING_INCOMING_CALL_FAILURE = 113
GET_NEW_SCRIPTID_FAILURE = 114
UNKNOWN_DATATYPE = 115
UNKNOWN_CALLTYPE = 116
TRAFFICSTATUS_FAILURE = 117
GETTING_MESSAGE_INFO_FAILED = 118
GETTING_MESSAGE_COUNT_FAILED = 119
SEND_MESSAGE_FAILED = 120
RECEIVE_MESSAGE_FAILED = 121
STOP_SCRIPT_FAILURE = 122
UNKNOWN_DIRECTION = 123
UNKNOWN_RESPONSE_CODE = 124
UNKNOWN_VARIABLE = 125
SUSPEND_CALL_FAILURE = 126
RESUME_CALL_FAILURE = 127

SERVER_ERROR_TEST_BED_NOT_STARTED = 300
SERVER_ERROR_MAPS_INIT_SCRIPT_NOT_FOUND = 301
SERVER_ERROR_PARSING_ERROR_IN_THE_MAPS_INIT_SCRIPT = 302
SERVER_ERROR_MAPS_SHUT_DOWN_SCRIPT_NOT_FOUND = 303
SERVER_ERROR_PARSING_ERROR_IN_THE_MAPS_SHUT_DOWN_SCRIPT = 304
SERVER_ERROR_SCRIPT_IS_ALREADY_STARTED_ON_THE_SAME_SCRIPTID = 305
SERVER_ERROR_SCRIPT_NOT_FOUND = 306
SERVER_ERROR_PROFILE_NOT_LOADED = 307
SERVER_ERROR_PARSING_ERROR_IN_THE_SCRIPT = 308
SERVER_ERROR_SCRIPT_NOT_AVAILABLE = 309
SERVER_ERROR_PARAMETER_LIST_EMPTY = 310

INT = "INT"
STRING = "STRING"
FLOAT = "FLOAT"
