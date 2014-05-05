import argparse
import yaml
import pycurl
import json #Temporary, remove me!
#TODO use voluptuous for structural validation of elements

#Map HTTP method names to curl methods
#Kind of obnoxious that it works this way...
HTTP_METHODS = {'GET' : pycurl.HTTPGET,
    'PUT' : pycurl.UPLOAD,
    'POST' : pycurl.POST,
    'DELETE' : 'DELETE'}

class Test:
    """ Describes a REST test """
    url  = None
    expected_status = [200] #expected HTTP status code or codes
    body = None #Request body, if any (for POST/PUT methods)
    headers = dict() #HTTP Headers
    method = "GET"
    group = 'Default'
    name = 'Unnamed'    
    validators = None #Validators for response body, IE regexes, etc
    benchmark = None #Benchmarking config for item
    #In this case, config would be used by all tests following config definition, and in the same scope as tests
    
    def __str__(self):
        print json.dumps(self)

class TestConfig:
    """ Configuration for a test run """
    timeout = 30 #timeout of tests, in seconds
    print_bodies = False #Print response bodies in all cases
    retries = 0 #Retries on failures
    verbose = False

    def __str__(self):
        print json.dumps(self)

class TestSet:
    """ Encapsulates a set of tests and test configuration for them """
    tests = list()
    config = TestConfig()

class BenchmarkConfig:
    """ Holds configuration specific to benchmarking of method """
    warmup_runs = 100 #Times call is executed to warm up
    benchmark_runs = 1000 #Times call is executed to generate benchmark results
    metrics = set() #Metrics to gather, TODO define these
    aggregates = set() #Aggregate options to report, TODO define these
    store_full = False #Store full statistics, not just aggregates
    #TODO output of full response set to CSV / JSON

    def __str__(self):
        print json.dumps(self)

class TestResponse:
    """ Encapsulates everything about a test response """   
    test = None #Test run
    response_code = None
    body = "" #Response body, if tracked -- TODO use chunk or byte-array storage
    passed = False
    response_headers = ""
    statistics = None #Used for benchmark stats on the method

    def __str__(self):
        print json.dumps(self)

    def body_callback(self, buf):
        """ Write response body by pyCurl callback """
        self.body = self.body + buf #TODO use chunk or byte-array storage

    def header_callback(self,buf):
        """ Write headers by pyCurl callback """
        self.response_headers = self.response_headers + buf #Optional TODO use chunk or byte-array storage

def read_test_file(path):
    """ Read test file at 'path' in YAML """
    #TODO Add validation via voluptuous
    #TODO Handle multiple test sets in a given doc
    teststruct = yaml.safe_load(read_file(path))
    return teststruct

def build_testsets(base_url, test_structure, test_files = set() ):
    """ Convert a Python datastructure read from validated YAML to a set of structured testsets
    The data stucture is assumed to be a list of dictionaries, each of which describes:
        - a tests (test structure)
        - a simple test (just a URL, and a minimal test is created)
        - or overall test configuration for this testset
        - an import (load another set of tests into this one, from a separate file)
            - For imports, these are recursive, and will use the parent config if none is present

    Note: test_files is used to track tests that import other tests, to avoid recursive loops 

    This returns a list of testsets, corresponding to imported testsets and in-line multi-document sets

    TODO: Implement imports (with test_config handled) and import of multi-document YAML """

    tests_out = list()
    test_config = TestConfig()    
    #returns a testconfig and collection of tests
    for node in test_structure: #Iterate through lists of test and configuration elements
        if isinstance(node,dict):
            node = lowercase_keys(node)
            for key in node:                
                if key == 'import':
                    importfile = node[key] #import another file
                    print 'Importing additional testset: '+importfile
                if key == 'url': #Simple test, just a GET to a URL
                    mytest = Test()
                    mytest.url = base_url + node[key]
                    tests_out.append(mytest)                                        
                if key == 'test': #Complex test with additional parameters
                    child = node[key]
                    mytest = make_test(base_url, child)                    
                    tests_out.append(mytest)                    
                if key == 'config' or key == 'configuration':
                    test_config = make_configuration(node[key])
                    print 'Configuration: ' + json.dumps(node[key])
    testset = TestSet()
    testset.tests = tests_out
    testset.config = test_config
    return [testset]

def make_configuration(node):
    """ Convert input object to configuration information """
    test_config = TestConfig()        

    node = lowercase_keys(flatten_dictionaries(node)) #Make it usable    

    for key, value in node.items():
        if key == 'timeout':
            test_config.timeout = int(value)
        elif key == 'print_bodies':
            test_config.print_bodies = bool(value)
        elif key == 'retries':
            test_config.retries = int(value)
        elif key == 'verbose':
            test_config.verbose = bool(value)

    return test_config

def flatten_dictionaries(input):
    """ Flatten a list of dictionaries into a single dictionary, to allow flexible YAML use
      Dictionary comprehensions can do this, but would like to allow for pre-Python 2.7 use 
      If input isn't a list, just return it.... """
    output = dict()
    if isinstance(input,list):
        for map in input:
            if not isinstance(map,dict):
                raise Exception('Tried to flatten a list of NON-dictionaries into a single dictionary. Whoops!')            
            for key in map.keys(): #Add keys into output
                    output[key]=map[key]
    else: #Not a list of dictionaries
        output = input;
    return output

def lowercase_keys(input_dict):
    """ Take input and if a dictionary, return version with keys all lowercase """
    if not isinstance(input_dict,dict):
        return input_dict

    safe = dict()
    for key,value in input_dict.items():
        safe[str(key).lower()] = value
    return safe 


def read_file(path): #TODO implementme, handling paths more intelligently
    """ Read an input into a file, doing necessary conversions around relative path handling """
    f = open(path, "r")
    string = f.read()
    f.close()
    return string

def make_test(base_url, node):
    """ Create a test using explicitly specified elements from the test input structure 
     to make life *extra* fun, we need to handle list <-- > dict transformations. 

     This is to say: list(dict(),dict()) or dict(key,value) -->  dict() for some elements 

     Accepted structure must be a single dictionary of key-value pairs for test configuration """
    mytest = Test()
    node = lowercase_keys(flatten_dictionaries(node)) #Clean up for easy parsing
    
    #Copy/convert input elements into appropriate form for a test object
    for configelement, configvalue in node.items(): 
        #Configure test using configuration elements            
        if configelement == 'url':
            mytest.url = base_url + str(configvalue)
        elif configelement == 'method': #Http method, converted to uppercase string
            mytest.method = str(configvalue).upper()                 
        elif configelement == 'group': #Test group
            mytest.group = str(configvalue)
        elif configelement == 'name': #Test name
            mytest.name = str(configvalue)
        elif configelement == 'validators':
            raise NotImplementedError() #TODO implement validators by regex, or file/schema match
        elif configelement == 'benchmark':
            raise NotImplementedError() #TODO implement benchmarking routines
        
        elif configelement == 'body': #Read request body, either as inline input or from file            
            if isinstance(configvalue, dict) and 'file' in lowercase_keys(body):
                mytest.body = read_file(body['file']) #TODO change me to pass in a file handle, rather than reading all bodies into RAM
            elif isinstance(configvalue, str):
                mytest.body = configvalue
            else:
                raise Exception('Illegal input to HTTP request body: must be string or map of file -> path')

        elif configelement == 'headers': #HTTP headers to use, flattened to a single string-string dictionary                         
            mytest.headers = flatten_dictionaries(configvalue)
        elif configelement == 'expected_status': #List of accepted HTTP response codes, as integers
            expected = list()
            #If item is a single item, convert to integer and make a list of 1
            #Otherwise, assume item is a list and convert to a list of integers
            if isinstance(configvalue,list):
                for item in configvalue:
                    expected.append(int(item))
            else:
                expected.append(int(configvalue))            
            mytest.expected_status = expected        

    #Next, we adjust defaults to be reasonable, if the user does not specify them

    #For non-GET requests, accept additional response codes indicating success 
    # (but only if not expected statuses are not explicitly specified)
    #  this is per HTTP spec: http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html#sec9.5
    if 'expected_status' not in node.keys():
        if mytest.method == 'POST':
            mytest.expected_status = [200,201,204]
        elif mytest.method == 'PUT':
            mytest.expected_status = [200,201,204]
        elif mytest.method == 'DELETE':
            mytest.expected_status = [200,202,204]

    return mytest



def run_test(mytest, test_config = TestConfig()):
    """ Run actual test, return results """
    if not isinstance(mytest, Test):
        raise Exception('Need to input a Test type object')
    if not isinstance(test_config, TestConfig):
        raise Exception('Need to input a TestConfig type object for the testconfig')
    
    #Check if we need to store the response body, otherwise we will discard it
    store_body = mytest.validators or test_config.print_bodies 

    curl = pycurl.Curl()
    curl.setopt(curl.URL,mytest.url)
    curl.setopt(curl.TIMEOUT,test_config.timeout)

    #if mytest.body:
    #TODO use file objects for CURLOPT_READDATA http://pycurl.sourceforge.net/doc/files.html
    #OR if not file, use CURLOPT_READFUNCTION


    #TODO Handle get/put/post/delete method settings
    #Needs to set curl.POSTFIELDS option to do a POST
    if mytest.method == 'POST':
        pass
    elif mytest.method == 'PUT':
        pass
    elif mytest.method == 'DELETE':
        curl.setopt(curl.CUSTOMREQUEST,'DELETE')
    
    if mytest.headers: #Convert headers dictionary to list of header entries, tested and working
        headers = list()
        for headername, headervalue in mytest.headers.items():
            headers.append(str(headername) + ': ' +str(headervalue))
        curl.setopt(curl.HTTPHEADER, headers) #Need to read from headers

    result = TestResponse()
    if not store_body: #Silence handling of response bodies, tested and working
        curl.setopt(pycurl.WRITEFUNCTION, lambda x: None)
    else: #Store the response body, for validation or printing
        curl.setopt(pycurl.WRITEFUNCTION, result.body_callback)
    curl.setopt(pycurl.HEADERFUNCTION,result.header_callback) #Gets headers
    
    try:
        curl.perform() #Run the actual call
    except Exception as e: 
        print e  #TODO figure out how to handle failures where no output is generated IE connection refused
        
    result.test = mytest
    response_code = curl.getinfo(pycurl.RESPONSE_CODE)
    result.response_code = response_code
    result.passed = response_code in mytest.expected_status 

    if test_config.print_bodies:
        print result.body

    curl.close()

    result.body = "" #Remove the body, we do NOT need to waste the memory anymore
    return result

def benchmark(curl, benchmark_config):
    """ Perform a benchmark, (re)using a given, configured CURL call to do so """
    curl.setopt(pycurl.WRITEFUNCTION, lambda x: None) #Do not store actual response body at all. 
    warmup_runs = benchmark_config.warmup_runs
    benchmark_runs = benchmark_config.benchmark_runs
    message = ''  #Message is name of benchmark... print it?

    # Source: http://pycurl.sourceforge.net/doc/curlobject.html
    # http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html -- this is the info parameters, used for timing, etc
    info_fetch = {'response_code':pycurl.RESPONSE_CODE,
        'pretransfer_time':pycurl.PRETRANSFER_TIME,
        'starttransfer_time':pycurl.STARTTRANSFER_TIME,
        'size_download':pycurl.SIZE_DOWNLOAD,
        'total_time':pycurl.TOTAL_TIME
    }

    #Benchmark warm-up to allow for caching, JIT compiling, etc
    print 'Warmup: ' + message + ' started'
    for x in xrange(0, warmup_runs):
        curl.perform()
    print 'Warmup: ' + message + ' finished'

    bytes = dict()
    speed = dict()
    time_pre = dict()
    time_server = dict()
    time_xfer = dict()

    print 'Benchmark: ' + message + ' starting'
    for x in xrange(0, benchmark_runs):
        curl.perform()
        if curl.getinfo(pycurl.RESPONSE_CODE) != 200:
            raise Exception('Error: failed call to service!')

        time_pretransfer = curl.getinfo(pycurl.PRETRANSFER_TIME) #Time to negotiate connection, before server starts response negotiation
        time_starttransfer = curl.getinfo(pycurl.STARTTRANSFER_TIME) #Pre-transfer time until server has generated response, just before first byte sent
        time_total = curl.getinfo(pycurl.TOTAL_TIME) #Download included

        time_xfer[x] = time_total - time_starttransfer
        time_server[x] = time_starttransfer - time_pretransfer
        time_pre[x] = time_pretransfer

        bytes[x] = curl.getinfo(pycurl.SIZE_DOWNLOAD) #bytes
        speed[x] = curl.getinfo(pycurl.SPEED_DOWNLOAD) #bytes/sec

        if print_intermediate:
            print 'Bytes: {size}, speed (MB/s) {speed}'.format(size=bytes[x],speed=speed[x]/(1024*1024))
            print 'Pre-transfer, server processing, and transfer times: {pre}/{server}/{transfer}'.format(pre=time_pretransfer,server=time_server[x],transfer=time_xfer[x])

    #print info
    print 'Benchmark: ' + message + ' ending'

    print 'Benchmark results for ' + message + ' Average bytes {bytes}, average transfer speed (MB/s): {speed}'.format(
        bytes=sum(bytes.values())/benchmark_runs,
        speed=sum(speed.values())/(benchmark_runs*1024*1024)
    )

    print 'Benchmark results for ' + message + ' Avg pre/server/xfer time (s) {pre}/{server}/{transfer}'.format(
        pre=sum(time_pre.values())/benchmark_runs,
        server=sum(time_server.values())/benchmark_runs,
        transfer=sum(time_xfer.values())/benchmark_runs
    )

    pass


def execute_tests(testset):
    """ Execute a set of tests, using given TestSet input """
    mytests = testset.tests
    myconfig = testset.config
    group_results = dict() #results, by group 
    group_failure_counts = dict()   

    #Initialize the dictionaries to store test fail counts and results
    for test in mytests:
        group_results[test.group] = list()
        group_failure_counts[test.group] = 0


    #Make sure we actually have tests to execute
    if not mytests:
        return None

    #Run tests, collecting statistics as needed
    for test in mytests: 
        result = run_test(test, test_config = myconfig)
        
        if not result.passed: #Print failure, increase failure counts for that test group
            print 'Test Failed: '+test.name+" URL="+test.url+" Group="+test.group+" HTTP Status Code: "+str(result.response_code)
            
            #Increment test failure counts for that group (adding an entry if not present)
            failures = group_failure_counts[test.group]
            failures = failures + 1
            group_failure_counts[test.group] = failures

        else: #Test passed, print results if verbose mode is on
            if myconfig.verbose:
                print 'Test Succeeded: '+test.name+" URL="+test.url+" Group="+test.group

        #Add to results for this test group to the resultset
        group_results[test.group].append(result)        

    #Print summary results
    for group in sorted(group_results.keys()):
        test_count = len(group_results[group])
        failures = group_failure_counts[group]
        if (failures > 0):
            print 'Test Group '+group+' FAILED: '+ str((test_count-failures))+'/'+str(test_count) + ' Tests Passed!'
        else:
            print 'Test Group '+group+' SUCCEEDED: '+ str((test_count-failures))+'/'+str(test_count) + ' Tests Passed!'



#Allow import into another module without executing the main method
if(__name__ == '__main__'):
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Base URL to run tests against")
    parser.add_argument("test", help="Test file to use")
    parser.add_argument("--verbose", help="Verbose output")
    args = parser.parse_args()
    test_structure = read_test_file(args.test)
    tests = build_testsets(args.url, test_structure)
    
    #Override testset verbosity if given as command-line argument
    if args.verbose: 
        tests.config.verbose = True

    #Execute batches of testsets
    for testset in tests:
        execute_tests(testset)    