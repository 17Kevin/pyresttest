import argparse
import yaml
import pycurl
import json
import StringIO

#Map HTTP method names to curl methods
#Kind of obnoxious that it works this way...
HTTP_METHODS = {u'GET' : pycurl.HTTPGET,
    u'PUT' : pycurl.UPLOAD,
    u'POST' : pycurl.POST,
    u'DELETE'  : 'DELETE'}

#Curl metrics for benchmarking, key is name in config file, value is pycurl variable
#Taken from pycurl docs, this is libcurl variable minus the CURLINFO prefix
# Descriptions of the timing variables are taken from libcurl docs:
#   http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html

METRICS = {
    #Timing info, precisely in order from start to finish
    #The time it took from the start until the name resolving was completed.
    'namelookup_time' : pycurl.NAMELOOKUP_TIME,

    #The time it took from the start until the connect to the remote host (or proxy) was completed.
    'connect_time' : pycurl.CONNECT_TIME,

    #The time it took from the start until the SSL connect/handshake with the remote host was completed.
    'appconnect_time' : pycurl.APPCONNECT_TIME,

    #The time it took from the start until the file transfer is just about to begin.
    #This includes all pre-transfer commands and negotiations that are specific to the particular protocol(s) involved.
    'pretransfer_time' : pycurl.PRETRANSFER_TIME,

    #The time it took from the start until the first byte is received by libcurl.
    'starttransfer_time' : pycurl.STARTTRANSFER_TIME,

    #The time it took for all redirection steps include name lookup, connect, pretransfer and transfer
    #  before final transaction was started. So, this is zero if no redirection took place.
    'redirect_time' : pycurl.REDIRECT_TIME,

    #Total time of the previous request.
    'total_time' : pycurl.TOTAL_TIME,


    #Transfer sizes and speeds
    'size_download' : pycurl.SIZE_DOWNLOAD,
    'request_size' : pycurl.REQUEST_SIZE,
    'speed_download' : pycurl.SPEED_DOWNLOAD,
    'speed_upload' : pycurl.SPEED_UPLOAD,

    #Connection counts
    'redirect_count' : pycurl.REDIRECT_COUNT,
    'num_connects' : pycurl.NUM_CONNECTS

    #TODO custom implementation for requests per second and server processing time, separate from previous?
}

#Map statistical aggregate to the function to use to perform the aggregation on an array
AGGREGATES = {
    'mean_arithmetic': #AKA the average, good for many things
        lambda x: float(sum(x))/len(x),
    'mean_harmonic': #Harmonic mean, better predicts average of rates: http://en.wikipedia.org/wiki/Harmonic_mean
        lambda x: 1/( sum([1/float(y) for y in x]) / len(x)),
    'median':  lambda x: median(x),
    'std_deviation': lambda x: std_deviation(x)
}

def median(array):
    """ Get the median of an array """
    sorted = [x for x in array]
    sort(sorted)
    floor = math.floor(len(sorted)/2) #Gets the middle element, if present
    if len(sorted) % 2 == 0: #Even, so need to average together the middle two values
        return float((sorted[floor]+sorted[floor-1]))/2
    else:
        return sorted[floor]

def std_deviation(array):
    """ Compute the standard deviation of an array of numbers """
    if not array or len(array) == 1:
        return 0

    average = AGGREGATES['mean_arithmetic'](array)
    variance = map(lambda x: (x-average)**2,array)
    stdev = AGGREGATES['mean_arithmetic'](variance)
    return setdev


class Test:
    """ Describes a REST test, which may include a benchmark component """
    url  = None
    expected_status = [200] #expected HTTP status code or codes
    body = None #Request body, if any (for POST/PUT methods)
    headers = dict() #HTTP Headers
    method = u'GET'
    group = u'Default'
    name = u'Unnamed'
    validators = None #Validators for response body, IE regexes, etc
    benchmark = None #Benchmarking config for item
    #In this case, config would be used by all tests following config definition, and in the same scope as tests

    def __str__(self):
        print json.dumps(self)

class TestConfig:
    """ Configuration for a test run """
    timeout = 10  # timeout of tests, in seconds
    print_bodies = False  # Print response bodies in all cases
    retries = 0  # Retries on failures
    verbose = False
    test_parallel = False  # Allow parallel execution of tests in a test set, for speed?

    def __str__(self):
        print json.dumps(self)

class TestSet:
    """ Encapsulates a set of tests and test configuration for them """
    tests = list()
    config = TestConfig()

class BenchmarkResult:
    """ Stores results from a benchmark for reporting use """
    aggregates = dict() #Aggregation recult, maps metricname to dictionary of aggregate --> result
    results = dict() #Benchmark output, map the metric to the result array for that metric
    failures = 0 #Track call count that failed

class BenchmarkConfig:
    """ Holds configuration specific to benchmarking of method
        warmup_runs and benchmark_runs behave like you'd expect

        Metrics are a bit tricky:
            - Key is metric name from Metric
            - Value is either a single value or a list:
                - list contains aggregagate name from AGGREGATES
                - value of 'all' returns everything
    """
    warmup_runs = 100 #Times call is executed to warm up
    benchmark_runs = 1000 #Times call is executed to generate benchmark results

    #Metrics to gather, must have one of them!
    metrics = dict()

    #TODO output of full response set to CSV / JSON

    def __str__(self):
        print json.dumps(self)

class TestResponse:
    """ Encapsulates everything about a test response """
    test = None #Test run
    response_code = None
    body = bytearray() #Response body, if tracked
    passed = False
    response_headers = bytearray()
    statistics = None #Used for benchmark stats on the method

    def __str__(self):
        print json.dumps(self)

    def body_callback(self, buf):
        """ Write response body by pyCurl callback """
        self.body.extend(buf)

    def unicode_body(self):
        return unicode(body,'UTF-8')

    def header_callback(self,buf):
        """ Write headers by pyCurl callback """
        self.response_headers.extend(buf) #Optional TODO use chunk or byte-array storage

def read_test_file(path):
    """ Read test file at 'path' in YAML """
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
        if isinstance(node,dict): #Each config element is a miniature key-value dictionary
            node = lowercase_keys(node)
            for key in node:
                if key == u'import':
                    importfile = node[key] #import another file
                    raise NotImplementedError('Nested test file imports not supported yet')
                    print u'Importing additional testset: '+importfile
                if key == u'url': #Simple test, just a GET to a URL
                    mytest = Test()
                    val = node[key]
                    assert isinstance(val,str) or isinstance(val,unicode)
                    mytest.url = base_url + val
                    tests_out.append(mytest)
                if key == u'test': #Complex test with additional parameters
                    child = node[key]
                    mytest = build_test(base_url, child)
                    tests_out.append(mytest)
                if key == u'config' or key == u'configuration':
                    test_config = make_configuration(node[key])
    testset = TestSet()
    testset.tests = tests_out
    testset.config = test_config
    return [testset]

def safe_to_bool(input):
    """ Safely convert user input to a boolean, throwing exception if not boolean or boolean-appropriate string
      For flexibility, we allow case insensitive string matching to false/true values
      If it's not a boolean or string that matches 'false' or 'true' when ignoring case, throws an exception """
    if isinstance(input,bool):
        return input
    elif isinstance(input,unicode) or isinstance(input,str) and unicode(input,'UTF-8').lower() == u'false':
        return False
    elif isinstance(input,unicode) or isinstance(input,str) and unicode(input,'UTF-8').lower() == u'true':
        return True
    else:
        raise TypeError('Input Object is not a boolean or string form of boolean!')


def make_configuration(node):
    """ Convert input object to configuration information """
    test_config = TestConfig()

    node = lowercase_keys(flatten_dictionaries(node))  # Make it usable

    for key, value in node.items():
        if key == u'timeout':
            test_config.timeout = int(value)
        elif key == u'print_bodies':
            test_config.print_bodies = safe_to_bool(value)
        elif key == u'retries':
            test_config.retries = int(value)
        elif key == u'verbose':
            test_config.verbose = safe_to_bool(value)

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

def build_test(base_url, node):
    """ Create a test using explicitly specified elements from the test input structure
     to make life *extra* fun, we need to handle list <-- > dict transformations.

     This is to say: list(dict(),dict()) or dict(key,value) -->  dict() for some elements

     Accepted structure must be a single dictionary of key-value pairs for test configuration """
    mytest = Test()
    node = lowercase_keys(flatten_dictionaries(node)) #Clean up for easy parsing

    #Copy/convert input elements into appropriate form for a test object
    for configelement, configvalue in node.items():
        #Configure test using configuration elements
        if configelement == u'url':
            assert isinstance(configvalue,str) or isinstance(configvalue,unicode) or isinstance(configvalue,int)
            mytest.url = base_url + unicode(configvalue,'UTF-8')
        elif configelement == u'method': #Http method, converted to uppercase string
            var = unicode(configvalue,'UTF-8').upper()
            assert var in HTTP_METHODS
            mytest.method = var
        elif configelement == u'group': #Test group
            assert isinstance(configvalue,str) or isinstance(configvalue,unicode) or isinstance(configvalue,int)
            mytest.group = unicode(configvalue,'UTF-8')
        elif configelement == u'name': #Test name
            assert isinstance(configvalue,str) or isinstance(configvalue,unicode) or isinstance(configvalue,int)
            mytest.name = unicode(configvalue,'UTF-8')
        elif configelement == u'validators':
            raise NotImplementedError('Validators not supported') #TODO implement validators by regex, or file/schema match
        elif configelement == u'benchmark':
            raise NotImplementedError('Benchmark input parsing not supported yet') #TODO implement benchmarking parsing

        elif configelement == u'body': #Read request body, either as inline input or from file
            #Body is either {'file':'myFilePath'} or inline string with file contents
            if isinstance(configvalue, dict) and u'file' in lowercase_keys(configvalue):
                var = lowercase_keys(configvalue)
                assert isinstance(var[u'file'],str) or isinstance(var[u'file'],unicode)
                mytest.body = read_file(var[u'file']) #TODO change me to pass in a file handle, rather than reading all bodies into RAM
            elif isinstance(configvalue, str):
                mytest.body = configvalue
            else:
                # TODO add ability to handle input of directories or file lists with wildcards to test against multiple bodies
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

    curl = pycurl.Curl()
    # curl.setopt(pycurl.VERBOSE, 1)  # Debugging convenience
    curl.setopt(curl.URL, str(mytest.url))
    curl.setopt(curl.TIMEOUT, test_config.timeout)


    #TODO use CURLOPT_READDATA http://pycurl.sourceforge.net/doc/files.html and lazy-read files if possible

    # Set read function for post/put bodies
    if mytest.method == u'POST' or mytest.method == u'PUT':
        curl.setopt(curl.READFUNCTION, StringIO.StringIO(mytest.body).read)

    if mytest.method == u'POST':
        curl.setopt(HTTP_METHODS[u'POST'], 1)
        curl.setopt(pycurl.POSTFIELDSIZE, len(mytest.body))  # Required for some servers
    elif mytest.method == u'PUT':
        curl.setopt(HTTP_METHODS[u'PUT'], 1)
        curl.setopt(pycurl.INFILESIZE, len(mytest.body))  # Required for some servers
    elif mytest.method == u'DELETE':
        curl.setopt(curl.CUSTOMREQUEST,'DELETE')

    headers = list()
    if mytest.headers: #Convert headers dictionary to list of header entries, tested and working
        for headername, headervalue in mytest.headers.items():
            headers.append(str(headername) + ': ' +str(headervalue))
    headers.append("Expect:")  # Fix for expecting 100-continue from server, which not all servers will send!
    headers.append("Connection: close")
    curl.setopt(curl.HTTPHEADER, headers)

    result = TestResponse()
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

    #print str(test_config.print_bodies) + ',' + str(not result.passed) + ' , ' + str(test_config.print_bodies or not result.passed)

    #Print response body if override is set to print all *OR* if test failed (to capture maybe a stack trace)
    if test_config.print_bodies or not result.passed:
        #TODO figure out why this prints for ALL methods if any of them fail!!!
        print result.body

    curl.close()

    result.body = None #Remove the body, we do NOT need to waste the memory anymore
    return result

def benchmark(curl, benchmark_config):
    """ Perform a benchmark, (re)using a given, configured CURL call to do so
    This is surprisingly complex, because benchmark allows storing metric to aggregate """

    warmup_runs = benchmark_config.warmup_runs
    benchmark_runs = benchmark_config.benchmark_runs
    message = ''  #Message is name of benchmark... print it?

    if (warmup_runs <= 0):
        raise Exception("Invalid number of warmup runs, must be > 0 :" + warmup_runs)
    if (benchmark_runs <= 0):
        raise Exception("Invalid number of benchmark runs, must be > 0 :" + benchmark_runs)

    #Initialize variables to store output
    output = BenchmarkResult()
    metricnames = list(benchmark_config.metrics.keys())
    metricvalues = [METRICS[name] for name in metricnames] #Metric variable for curl, to avoid hash lookup for every metric name
    results = [list() for x in xrange(0, len(metricnames))] #Initialize arrays to store results for each metric

    curl.setopt(pycurl.WRITEFUNCTION, lambda x: None) #Do not store actual response body at all.

    #Benchmark warm-up to allow for caching, JIT compiling, on client
    print 'Warmup: ' + message + ' started'
    for x in xrange(0, warmup_runs):
        curl.perform()
    print 'Warmup: ' + message + ' finished'

    print 'Benchmark: ' + message + ' starting'

    for x in xrange(0, benchmark_runs): #Run the actual benchmarks

        try: #Run the curl call, if it errors, then add to failure counts for benchmark
            curl.perform()
        except Exception:
            output.failures = output.failures + 1
            continue #Skip metrics collection

        # Get all metrics values for this run, and store to metric lists
        for i in xrange(0, len(metricnames)):
            results[i].append( curl.getinfo(metricvalues[i]) )

    #print info
    print 'Benchmark: ' + message + ' ending'


    #Compute aggregates from results, and add to BenchmarkResult
    # If it's storing all values (aggregate 'all'), it is added to BenchmarkResult.results arrays
    # Otherwise, a dict {aggregate1:value1, aggregate2:value2...} is added to BenchmarkResult.aggregates[metricname]
    for i in xrange(0,len(metricnames)):
        metric = metricnames[i]
        aggregates = benchmark_config.metrics[metric]
        result_array = results[i]

        #Convert aggregates to list, so we can iterate over them, even if single element
        if not isinstance(aggregates,list) or isinstance(aggregates,set):
            aggregates = [aggregates]

        aggregate_results = dict()

        #Compute values for all aggregates, apply aggregation function to the results array and store
        for aggregate_name in aggregates:
            aggregate_function = AGGREGATES[aggregate_name]
            if aggregate_name == 'all': #Add to the results arrays storing full results
                output.results[metric]=result_array
            else:
                aggregate_results[aggregate_name] = aggregate_function(result_array)

        #Add aggregate-value mappings for this metric to output
        output.aggregates[metric] = vals

    return output

def execute_tests(testset):
    """ Execute a set of tests, using given TestSet input """
    mytests = testset.tests
    myconfig = testset.config
    group_results = dict() #results, by group
    group_failure_counts = dict()

    #Make sure we actually have tests to execute
    if not mytests:
        return None

    #Initialize the dictionaries to store test fail counts and results
    for test in mytests:
        group_results[test.group] = list()
        group_failure_counts[test.group] = 0

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

        #Add results for this test group to the resultset
        group_results[test.group].append(result)

    #Print summary results
    for group in sorted(group_results.keys()):
        test_count = len(group_results[group])
        failures = group_failure_counts[group]
        if (failures > 0):
            print u'Test Group '+group+u' FAILED: '+ str((test_count-failures))+'/'+str(test_count) + u' Tests Passed!'
        else:
            print u'Test Group '+group+u' SUCCEEDED: '+ str((test_count-failures))+'/'+str(test_count) + u' Tests Passed!'



#Allow import into another module without executing the main method
if(__name__ == '__main__'):
    parser = argparse.ArgumentParser()
    parser.add_argument(u"url", help="Base URL to run tests against")
    parser.add_argument(u"test", help="Test file to use")
    parser.add_argument(u"--verbose", help="Verbose output")
    parser.add_argument(u"--print-bodies", help="Print all response bodies", type=bool)
    args = parser.parse_args()
    test_structure = read_test_file(args.test)
    tests = build_testsets(args.url, test_structure)


    # Override configs from command line if config set
    for t in tests:
        if args.verbose:
            t.config.verbose = True

        if args.print_bodies:
            t.config.print_bodies = args.print_bodies

    #Execute batches of testsets
    for testset in tests:
        execute_tests(testset)
