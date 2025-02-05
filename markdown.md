## Contents

> Related Documents
>
> Overview
>
> Processing
>
> Signals
>
> Tuxedo Event Handling
>
> Termination
>
> Cache Recovery
>
> Commands
>
> Configuration Parameters
>
> Command-line Arguments
>
> Built-in Functions
>
> Pre-loaded Functions
>
> Broker Functions
>
> Database Functions

* * *

## Related Documents

> SAS for the Customer Node Module
>
> UTP Test Plan

[Contents]

* * *

## Overview

  

An event rating broker (ERB) process is the overseer of the operation of event
rating. Multiple broker processes can be configured to run on one Singleview
instance. On startup the broker creates or attaches to the shared memory
segment used by the event rating broker module and starts the ENM, ERT and ERO
processes that have been configured for that broker. If no ENM, ERT and ERO
processes are associated with the broker, the broker does not create or attach
to any ERB shared memory segment. If all processes are running on the one
machine, the broker performs no other function other than to monitor the other
processes, and to pass external commands onto the appropriate rating process
(via ERB module calls).  
  
[Contents]

* * *

## Processing

On startup, the broker interprets its command-line arguments. The broker then
attempts to create a lock file in the log directory.  The name of the lock
file contains the sequence number of the broker. If the lock file already
exists, or cannot be created, the broker logs an error message and terminates.

Once the lock file has been created, the broker establishes its signal
handler, then connects to the TRE and calls the biLicenceStatus&() function to
verify licence information. If the licence information verification fails
during startup, then the broker will fail to start. The licence information
will also be verified every 24 hours (not in non-database mode) and log an
error if verification fails, however the broker will not automatically
terminate.

The broker then creates an internal event pipe.  When waiting for input, the
broker performs a _select()_ on a set of file descriptors, including the input
socket and the internal event pipe.  By writing a small amount of data (one
byte) to the internal event pipe, the broker can be interrupted.  The internal
event pipe is used to interrupt the broker in the case of receipt of an
unsolicited Tuxedo event or a pending response in the event cache to a command
sent to the ENM, ERT or ERO.

The broker then subscribes to appropriate Tuxedo events and initialises a
Tuxedo event handler to capture event details.

The broker then connects to the database and calls SQLConnection::EnableFAD()
in order to support automatic detection of database instance failure (Failure
Auto-Detection, or FAD), if enabled.  The broker then loads some functions in
order to ensure normal processing in FAD mode.

The broker reads the values of its configuration attributes. If the
CACHE_START configuration attribute is TRUE, then this broker is responsible
for creating the derived attribute table, service, customer node, account,
rating subtotal and temporal entitlement shared memory caches used by the
rating processes for the Singleview instance:

  * The broker retrieves configuration details for the caches to be created from the BKR, SERVICE_CACHE, CUSTOMER_CACHE, ACCOUNT_CACHE, SUBTOTAL_CACHE and ENTITLEMENT_CACHE configuration items.  In a multiple instance CB environment, the broker retrieves the configuration details for each cache that is configured for the specified instance on which the broker is running.  For example if the broker is being run on the "MASTER" instance, the broker retrieves the configuration of the SERVICE_CACHE that is configured for the "MASTER" instance.  In a single instance CB environment, the broker retrieves configuration details from configuration item 1 for each of the SERVICE_CACHE, ACCOUNT_CACHE, SUBTOTAL_CACHE, CUSTOMER_CACHE and ENTITLEMENT_CACHE configuration items.  There should only be one of each of these configuration items configured in a single instance environment.  If the broker fails to find a suitable configuration item for any of these caches then it uses appropriate default values for the relevant configuration attributes.
  

  * The broker attempts to create the derived attribute table, service, customer node, rating subtotal, account and temporal entitlement shared memory caches used via calls to the DatGlobalSharedCache::Open(), scm_open(), cnm_open(), rsc_open(), acm_open() and tec_open() functions (respectively).  These caches contain some global data structures that result in inter-process contention.  In order to reduce contention, some of these structures in the temporaral entitlements cache, account cache and rating subtotal cache are "sharded" (or fragmented) into a number of smaller structures.  The broker derives the number of smaller structures to use by reading the value of the `ATA_RATING_CACHE_SHARD_CNT` environment variable; if this variable is undefined then a default value of 3 is used.  The value of the _max_stream_cnt_ parameter passed to acm_open(), rsc_open() and tec_open() is 512 (for concurrent streams opened by transactional rating servers) plus the value returned from the erb_get_transaction_limit() for all of the broker processes that are configured for the Singleview instance on which this broker process is running. 
  

  * If the broker fails to create the caches, it attempts to attach to them (via calls to the DatGlobalSharedCache::Attach(), scm_attach(), cnm_attach(), rsc_attach(), acm_attach() and tec_attach() functions). If any attach attempt fails then the broker detaches from any cache to which it has attached and then aborts.
  

If there are any ENM, ERT or ERO processes associated with the broker and if
the CACHE_START configuration attribute for the broker is FALSE then the
broker attempts to attach to the derived attribute table, service, customer
node, rating subtotal, account and temporal entitlement shared memory caches
(using the functions described in the previous paragraph).  If any attach
attempt fails then the broker detaches from any cache to which it has attached
and then aborts.  An ENM, ERT or ERO process is considered associated with the
broker if it has the same value of BKR_INSTANCE attribute as the sequence
number of this broker.

If there are any ENM, ERT or ERO processes associated with the broker and if
the CACHE_START configuration attribute for the broker is TRUE then the broker
terminates any ENM, ERT and ERO processes that are associated with the broker
and that are still running, then removes any pre-existing event cache (via
calls to the erb_exists() and erb_destroy() functions).  The broker then
creates (via a call to the erb_create() function) an event cache.  The broker
then checks the ENABLED boolean configuration attribute of all ENM, ERT and
ERO processes defined for this broker in the database.  All ERT, ERO and ENM
processes with a value of TRUE for this attribute are started by the broker.
The broker then waits up to STARTUP_TIMEOUT seconds for these processes to
attach to the event cache.

The broker does not create (or attach to) an event cache if there are no
associated ENM, ERT or ERO processes. This allows one broker to be responsible
for the DAT, SCM, ACM, CNM, RSC and TEC caches and other brokers to be
responsible for ENM, ERT and ERO processes.

The broker registers several built-in functions in its expression parser.

The broker then creates a Unix-domain socket named `bkr<seqnr>.sok` in the
directory specified by the value of the `ATA_DATA_SERVER_CONFIG` environment
variable and commences listening for incoming connections on this socket.
Processes may connect to the broker and send commands or command responses
(see Commands).  When a process connects the broker initiates a _session_ for
that connection.  The session is terminated when the socket connection is
closed.

For each session the broker stores in a queue a copy of each received command
if that command is expecting a response from its destination.  When the broker
receives a response to one of these commands, the broker deletes from the
queue the matching command.  When a child process of the broker terminates
then the broker checks the command queue of every current session for commands
that were sent to this child process.  For each such command the broker sends
an appropriate response to the originator of the command.

If CACHE_START is TRUE then every EXPIRY_POLL seconds the broker:

  1. calls acm_stream_close_expired() to rollback and close any local and remote account rating streams that have been inactive for more than STREAM_EXPIRY_PERIOD (calling rsc_stream_close() and tec_stream_close() to close associated streams in the RSC and TEC, respectively); and
  2. calls acm_reservation_delete_expired() to delete any reservations from the account, rating subtotal cache and temporal entitlement cache that have not been updated for more than RESERVATION_EXPIRY_PERIOD seconds, and have exceeded their expiry date. For any deleted reservations, the user-defined EPM function specified by RESERVATION_EXPRY_FUNC is evaluated as at the current date/time.

Once the broker has started successfully it calls the BKR.Startup& EPM
function.  This in turn calls the BKRStarted& function in each trerate and
trerate_tran server (via a Tuxedo event) notifying the servers that they can
attach to the cache.

[Contents]

* * *

## Termination

During termination, the broker:

  1. calls the biCacheDetach& EPM function if CACHE_START is TRUE;
  2. disconnects from the TRE;
  3. ceases listening for incoming socket connections;
  4. sends a termination signal to its child processes and a notification to any rate-and-store trerate processes then waits up to SHUTDOWN_TIMEOUT seconds for them to detach from the ERB module;
  5. detaches any lingering child processes from the ERB module;
  6. terminates any running ENM, ERT and ERO processes attached to this broker;
  7. removes the ERB module.
  8. removes the derived attribute table, service, customer node, rating subtotal, account and temporal entitlement caches if CACHE_START is TRUE.
  9. disconnects from the database; and
  10. removes the lock file.

[Contents]

* * *

## Signals

On receipt of a SIGTERM signal the broker terminates. It will wait for all its
children to terminate.

On receipt of a SIGQUIT signal the broker terminates. If a prior SIGTERM has
been seen then it will NOT wait for all its children to terminate. If not then
a normal SIGTERM shutdown will occur. This is sent by the BMP when it deems
the response to the initial SIGTERM has taken too long.

If the SIGQUIT signal takes too long then a SIGKILL will be sent, which will
terminate immediately.

On receipt of a SIGINT signal, the BKR writes data to its internal event pipe.
SIGINT is used by the child ENM, ERT and ERO processes to asynchronously
signal the BKR that a command response is waiting for the BKR in the event
cache.

The broker ignores SIGHUP, SIGUSR1, SIGUSR2 and SIGPIPE signals.

[Contents]

* * *

## Tuxedo Event Handling

When the broker process connects to the TRE it uses the treConnectFlags() API
call to specify that it is to be notified of unsolicited messages via thread
notification.  It then subscribes to four events: "ERB", "ERB:<seqnr>", "BKR",
and "BKR:<seqnr>, and sets up an unsolicited message handler. Hence using
treEventPostx&(), it is possible to send unsolicited messages to all ERB
processes (using the "ERB"/"BKR" event name), or to direct a message to an
individual ERB (using the "ERB:<ProcessNr>"/"BKR:<ProcessNr>" event name).

When the broker process receives an unsolicited message the event thread adds
the event details to a list of pending events. Tuxedo has significant
restrictions on what Tuxedo calls can be made in the unsolicited message
handler, so it is not possible to immediately process the event.  The main
thread is then interrupted by the event handler by interrupting the select
call on which the process is blocking.

Prior to checking for a pending socket event, the broker process checks to see
if it has received a Tuxedo event.   If it has, it interprets the first event
parameter as the name of an EPM function to call and the remaining parameters
as the parameters to that function.  The broker process then calls the
EvaluateFunction() method in its internal parser to parse and evaluate the
function.  If this fails, it logs a message including the error details from
the failed call.  The result from the function is ignored.

[Contents]  

* * *

## Cache Recovery

The BKR and the processes managed by the BKR - the ENM, ERT and ERO - use
shared memory segments for inter-process communication.  Spin-locks are used
within the shared memory segments (caches) to allow shared access to cached
data.  If a process attached to one of these caches terminates abnormally, it
is possible that it was holding locks at the time of termination.  If the
locks are left, other processes attempting to obtain that lock will block
indefinitely.

It is the responsibility of the parent BKR to perform automatic cache recovery
to attempt to recover locks left by abnormally terminated child processes.
When a BKR detects abnormal termination of a child process it will:

  * If a core file exists in $ATA_DATA_SERVER_LOG, rename the core file to core.<processname>.<timestamp> so that problem analysis is possible;
  * Call the cache recovery functions in each of the shared memory caches. This is achieved by calling: CacheRecover$[](ProcessId&) which then calls the following:
    * EventCacheRecover$[](EventCacheSeqNr&, ProcessId&)
    * DerivedTableCacheRecover$[](ProcessId&)
    * AccountCacheRecover$[](ProcessId&)
    * CustomerNodeCacheRecover$[](ProcessId&)
    * ServiceCacheRecover$[](ProcessId&)
    * SubtotalCacheRecover$[](ProcessId&)
    * EntitlementCacheRecover$[](ProcessId&)
  * Log the output of the recovery functions.

[Contents]  

* * *

## Commands

The following commands can be received by the broker:  

  1. _terminate_

Causes the broker process to terminate.  
  

  2. _start <type> <number>_

The broker starts a process of the type specified by _type_ using a process
number of _number_ (for example, ENM 2).  
  

  3. _end <type> <number>_

The broker terminates the process specified specified by _type_ and _number_
(for example, ENM 2). The process to be terminated must have been started by
the broker.  
  

  4. Commands to be sent to ENM, ERT or ERO processes 

The broker transmits these commands onto the destination process specified by
process type and process number. If the process number is -1, the broker
transmits the command to _all_ child processes of the specified type.  
  

  5. Responses to commands sent to ENM, ERT or ERO processes 

The broker receives these responses from its child ENM, ERT and ERO processes.
The broker transmits these responses via the same socket connection on which
the original command was received.

  

[Contents]

* * *

## Configuration Parameters

The broker reads from the database configuration attributes for several
configuration items:

### BKR Configuration Parameters

Configuration Item Type | Attribute Name | Description  
---|---|---  
BKR | ENABLED | A boolean value used by the BMP.  If this value is TRUE (1) then the BMP automatically starts this broker process.  If no value is supplied for this attribute then its value is assumed to be FALSE (0).  
BKR | INSTANCE | A character string specifying the name of the Singleview instance on which this process is to be run.  This is not required if there is only a single Singleview instance.  
BKR | PROCESS_ENVIRONMENT | Optional additional environment variables which will be exported prior to starting this process (used by BMP).  
BKR | PROCESS_NAME | The name of the process (used by BMP).  
This value should always be set to `bkr`.  
BKR | COMMAND_LINE_ARGS | Optional command line arguments (such as debug level) used when the process is started (used by BMP).  
BKR | WAIT_PERIOD | The integer number of seconds the BMP will wait after starting this process before it starts the next process (used by BMP).  If no value was supplied for this attribute then its value is assumed to be zero.  
BKR | CACHE_START | If TRUE (1) this BKR is responsible for creating the derived attribute table, account, customer node, rating subtotal, temporal entitlement and service caches.  Only one BKR on an instance can be configured to create the shared-memory caches.  The BMP starts this BKR before starting all other BKR processes. If no value is supplied for this attribute then its value is assumed to be FALSE (0). It is suggested that the BKR which manages the caches does not have any associated ENMs, ERTs or EROs.  
BKR | SHARED_DA_CACHE_TABLE_LIMIT | The maximum number of derived attribute definitions that can be stored in the derived attribute table shared memory cache, which is effectively the number of derived attribute tables that can be stored. In a multi-tenanted deployment, however, there can be multiple tenant specific tables per derived attribute definition, in which case this value is the number of derived attribute definitions that can be stored; not tables.This attribute must be set to a positive value if any derived attribute tables are configured to be stored in shared memory. This attribute is only applicable if CACHE_START is TRUE. Default: 100  
BKR | SHARED_DA_CACHE_POOL_SIZE | The size in bytes of the shared memory pool used in the derived attribute table shared memory cache.  The 'M' suffix can be used to specify a size in megabytes.This attribute must be set to a positive value if any derived attribute tables are configured to be stored in shared memory. This attribute is only applicable if CACHE_START is TRUE. Default: 10M  
BKR | EVENT_CACHE_POOL_SIZE | The size in bytes of the event cache memory pool.Allocations are made from this memory pool for event, charge and command records, use to transfer information between the BKR, ENM, ERT and ERO processes. If this pool becomes full, then ENMs and ERTs may stall until the ERO has performed some output and freed events and charges to the pool. BKR statistics (ie $ getstats -server BKR) should be used to determine the optimum pool size. The event cache is only created by the BKR if the BKR has associated ENM, ERT or ERO processes. The suffix 'M' can be used to indicate megabytes.  Default is 1M.  
BKR | STARTUP_TIMEOUT | The maximum period of time (in seconds) for which the broker process waits for enabled ERT, ERO and ENM processes to attach to the ERB module after being started. Default value is 20 seconds.  
BKR | SHUTDOWN_TIMEOUT | The maximum period of time (in seconds) for which the broker process waits while shutting down for ENM, ERT, ERO and RAS processes to detach and for socket connections to be closed. Once this timeout period has elapsed, the broker closes all open socket connections, detaches any processes that have not yet detached from the shared memory segment, and terminates. If the value of this attribute is zero, the broker will not pause while shutting down.   
Default is 120 seconds.  
BKR | INACTIVITY_TIMEOUT | Period of time (in seconds) after which an idle socket connection will be disconnected. The inactivity timeout is not applicable for requests that require a response.The default is 60 seconds. If the value of this attribute is zero, inactivity timeouts will not occur.  
BKR | MAX_SOCKETS | Maximum number of simultaneous socket connections to be supported by the broker. Default is 50.   
BKR | ERROR_HANDLE_FUNCTION | The name of a function that is to be called when the BKR logs an error message. The function must have an interface of:  
  
`<FunctionName>&(ErrorId&, ErrorMessage$)`  
  
The first parameter is the ID of the error; the second parameter is the error
message. The default function for new "BKR" configuration items is
BKR.ErrorHandle&.  
BKR | MAX_PROCESSES | Maximum number of processes that can attach simultaneously to the event cache created by this broker process. Default is 100.  
BKR | TRANSACTION_LIMIT | The maximum number of open transactions supported simultaneously by the event cache created by this broker process. Default is 100.  
  


**

SERVICE_CACHE Configuration Parameters

** Configuration Item Type | Attribute Name | Description  
---|---|---  
SERVICE_CACHE | INSTANCE | The name of the CB instance in the CB cluster. Not required if there is only a single CB instance.  
SERVICE_CACHE | SERVICE_POOLSIZE | The size of the cache in bytes for storing service details.    The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 5M. In general, the size should be chosen to allow current details for all active services to be cached.   The space required for each service is configuration dependent as well as being dependent on the the actual fields being cached (see SERVICE_FIELD_NAMES).  As a general rule of thumb allow 512 bytes per service. In a multi-instance deployment, this cache will by default only cache details for services associated with customer partitions being managed by this instance.   However, the CACHE_ALL_PARTITIONS setting can change this behaviour.  
SERVICE_CACHE | SERVICE_DA_POOLSIZE | The size of the cache in bytes for storing service derived attribute details (also known as service lists) and companion product instance details.  The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 1M. This cache is also used for caching companion product details (general field settings) associated with each service. This cache is primarily used in rating.  It is not used by the bgp.  It should be sized to allow all current service derived attribute and companion product details accessed by the rating configuration to be cached for all active services. In a multi-instance deployment, this cache will by default only cache details for service derived attribute details associated with customer partitions being managed by this instance.  However, the CACHE_ALL_PARTITIONS setting can change this behaviour.  
SERVICE_CACHE | SERVICE_NAME_POOLSIZE | The size of the cache in bytes for storing the mapping from service names to service identifiers for all services in the system.   The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 1M. The size should be chosen to allow name to id mapping details for all active services for all instances to be cached.   Allow approximately 100 bytes per entry.  
SERVICE_CACHE | NETWORK_NAME_POOLSIZE | The size of the cache in bytes for storing the mapping from service network names to service identifiers for all services in the system.    The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 1M. This cache is only used if the NETWORK_NAME field of SERVICE records are used, and services need to be identified by NETWORK_NAME during rating.  If this is the case, this attribute should be sized similarly to SERVICE_NAME_POOLSIZE.  
SERVICE_CACHE | SERVICE_FIELD_NAMES | Specifies a subset of field names from the SERVICE_HISTORY_V view that are intended to be cached in the Service cache. This attribute must be an expression returning a string array. If the expression is undefined or returns an empty array, every field in the SERVICE_HISTORY_V view will be cached.  
  
For best performance and optimal use of shared memory, the SERVICE_FIELD_NAMES
should be set to the minimal set of service fields which are required.
Whenever service details are fetched from the service cache, the full set of
service fields must be decoded.  The smaller the number of fields, the more
efficient the service fetch.The setting of SERVICE_FIELD_NAMES affects the
size of an encoded service record, so modifying this attribute may also
require the modification of SERVICE_POOLSIZE.  
  
The default expression for this field in new configuration items of this type
is SERVICE_CACHE.FieldNames$[]().  
SERVICE_CACHE | CACHE_ALL_PARTITIONS | If set to 1 (true), allow caching of service details and service DA details (including service product details) from any instance, not just the partitions associated with the local instance, regardless of the status of customer partitions. This configuration attribute is read from the database and updated in the service cache whenever any process (such as a trerate) attaches to the service cache.  If this attribute is modified, performing a server restart (using biServerRestart&) of all trerate servers advertising biCache is sufficient to update the service cache and refresh any cached configuration item information that would affect service purging.  Optional.  Default is 0 (false).  Undefined implies 0 (false).  
  


****

**ACCOUNT_CACHE Configuration Parameters **



****

**SUBTOTAL_CACHE Configuration Parameters**



**

CUSTOMER_CACHE Configuration Parameters

** Configuration Item Type | Attribute Name | Description  
---|---|---  
CUSTOMER_CACHE | INSTANCE | The name of the CB instance in the CB cluster. Not required if there is only a single CB instance.  
CUSTOMER_CACHE | CUSTOMER_POOLSIZE | The size of the cache in bytes for storing customer details accessed during rating.  The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 3M. When real-time rating is used and rating latency is important, there should be sufficient space in the customer cache to store all current customer information (assuming customer cache lookups are required for rating). The space required per customer is dependent on the setting of CUSTOMER_FIELD_NAMES.  As a rule of thumb, allow 300 bytes per customer record.   
CUSTOMER_CACHE | CUSTOMER_DA_POOLSIZE | The size of the cache in bytes for storing customer derived attribute details accessed during rating.  The suffixes K, M and G are supported for specifying sizes in kilobytes, megabytes and gigabytes respectively.  Default is 1M. This attribute will only need to be increased if customer DA tables are used and accessed during rating.  In this case, the cache  should be sized to allow the necessary derived attribute details to be cached for all active customers.  
CUSTOMER_CACHE | CUSTOMER_FIELD_NAMES | Specifies a subset of field names from the CUSTOMER_NODE_CACHE_V view that are intended to be cached in the Customer Node cache. This attribute must be an expression returning a string array.  In addition to the fields specified by this attribute, certain special fields are also cached. Only these special fields are cached if no value is supplied for the CUSTOMER_FIELD_NAMES attribute. For best performance and optimal use of shared memory, the CUSTOMER_FIELD_NAMES should be set to the minimal set of customer fields which are required.  Whenever customer details are fetched from the customer cache, the full set of customer fields must be decoded.  The smaller the number of fields, the more efficient the customer fetch. The setting of CUSTOMER_FIELD_NAMES affects the size of an encoded customer record, so modifying this attribute may also require the modification of CUSTOMER_POOLSIZE.  
  
The default expression for this field in new configuration items of this type
is CUSTOMER_CACHE.FieldNames$[]().  
CUSTOMER_CACHE | CACHE_ALL_PARTITIONS | If set to 1 (true), allow caching of customer node details and customer node DA details from any instance, not just the partitions associated with the local instance, regardless of the status of customer partitions. This configuration attribute is read from the database and updated in the customer node cache whenever any process (such as a trerate) attaches to the customer node cache.  If this attribute is modified, performing a server restart (using biServerRestart&) of all trerate servers advertising biCache is sufficient to update the customer node cache and refresh any cached configuration item information that would affect customer node purging.  Optional.  Default is 0 (false).  Undefined implies 0 (false).  
CUSTOMER_CACHE | BILL_RUN_END_BEFORE_BILL_DATE | This attribute affects the calculation of the BILL_RUN_START_DATE and BILL_RUN_END_DATE  values for a customer.  It can be used to align the bill-cycle used in rating subtotal calculation with the bill-cycle used by the RGP (RENTAL_END_BEFORE_BILL_DATE) and BGP (USAGE_CHARGES_BEFORE_BILL_DATE) processes.If this attribute is FALSE (0), and the bill-run effective date has a time component of 23:59:59, then the BILL_RUN_START_DATE will be one second after the bill-run effective date (time component of 00:00:00) and the BILL_RUN_END_DATE will be equal to the bill-run effective date (time component of 23:59:59). Otherwise, the BILL_RUN_END_DATE will be one second before the bill-run effective date. Default is TRUE (1). See the SAS for the Customer Node Module for more details on this attribute.  
**



**

**ENTITLEMENT_CACHE Configuration Parameters**



[Contents]

* * *

## Command-line Arguments

The syntax for executing the broker is as follows:  

> `BKR <sequence number> [-?] [-d <debug level>]`

The `<sequence number>` argument is the unique identifier for an instantiation
of the broker process. The broker will start only its associated ENM, ERT and
ERO processes.

The `-?` argument causes a usage message to be written to stderr. The broker
terminates immediately.

The `<debug level>` argument is an integer value or comma-separated string of
mnemonics which controls the amount of debug information written to the file
`$ATA_DATA_SERVER_LOG/BKR.trc`.

The value of `<debug level>` is interpreted as the sum of the following
levels:  


Decimal | Hexadecimal | Octal | Mnemonic | Description  
---|---|---|---|---  
1 | 0x01 | 0001 | RDB | Oracle tracing  
2 | 0x02 | 0002 | SOK | TCP/IP socket tracing  
4 | 0x04 | 0004 | CLD | Child process operations  
8 | 0x08 | 0010 | CAC | Cache operations  
16 | 0x10 | 0020 | TMO | Timeout alarms  
32 | 0x20 | 0040 | OP | General operations  
64 | 0x40 | 0100 | EPM | Expression parser tracing  
128 | 0x80 | 0200 | EPM_LIGHT | Expression parser tracing excluding function parameter values and return values  
255 | 0xFF | 0377 | ALL | All trace levels  
  
For example, all of the following represent the same debug level (Oracle and
Expression parser tracing):

  * -d 65
  * -d 1,64
  * -d RDB,EPM

[Contents]

* * *

## Built-in Functions

These functions are registered with the internal expression parser prior to
any expressions being evaluated.

Additional built-in functions are provided by the ERB module.  Refer to this
module for further details.  
  
  

### Function BkrTrace&

****

**Declaration**

    
    
    BkrTrace&(DebugLevel&)
    BkrTrace&(DebugLevel$)

****

**Parameters**  

  
DebugLevel& | Diagnostic debug level (as an integer)  
---|---  
DebugLevel$ | Diagnostic debug level (as comma-separated mnemonics)  
  
**Returns**

Returns 1.

**Description**

This function sets the diagnostic debug level for this broker to the level
specified by DebugLevel& (integer) or DebugLevel$ (comma-separated mnemonics).
This value is interpreted in the same manner as the `<debug level>` command-
line argument. A value of DebugLevel& that is less than or equal to zero or
DebugLevel$ that is an empty string will deactivate diagnostic tracing for the
process.  


**Implementation**

This function is implemented as a built-in function.

[Contents]

* * *

### Function BKRProcessNr&

** **

****

**Declaration**

    
    
    BKRProcessNr&()

****

**Parameters**

None.

**Returns**

Returns the process number passed to the BKR on its command line.

**Description**

This function returns the process number of the current BKR process.  It is
used by the statistics gathering function when logging information to the
TREMON process.

**Implementation**

This function is implemented as a built-in function.  It is registered by the
BKR process so the function is only available in the rating environment.

[Contents]  

* * *

### Function DatabaseConnect&

**Declaration**

    
    
    DatabaseConnect&()
    DatabaseConnect&(ConnectString$)

**Parameters**

ConnectString$ | Connection string for database instance.  
---|---  
  
**Description**

The DatabaseConnect& function is used to connect the rating processes to the
database.  The BKR process will attach to the database and call
erb_database_on() to set the ERB into database mode and also to send commands
to any ENM, ERT and ERO processes to also connect to the database.  If a value
is defined for ConnectString$ then it is supplied as the parameter to
erb_database_on().

**Return Value**  
  
Always 1.  An EPM exception is generated on error.

[Contents]  

* * *

### Function DatabaseDisconnect&

**Declaration**

    
    
    DatabaseDisconnect&()

**Parameters**

None.

**Description**

The DatabaseDisconnect& function is used to disconnect the rating processes
from the database.  The BKR process will disconnect from the database and call
erb_database_off() to set the ERB into non-database mode and also to send
commands to any ENM, ERT and ERO processes to also disconnect from the
database.

**Return Value**  
  
Always 1.  An EPM exception is generated on error.

[Contents]  

* * *

## Pre-loaded Functions

These functions are pre-loaded into the parser prior to use by the broker.
This is to avoid the need for database access on the death of a child process
or after a FAD event.

  * AccountInconsistencyCheck&
  * CacheRecover$
  * DatabaseConnect&
  * DatabaseDisconnect2&
  * DatabasePing&
  * ERROR_HANDLE_FUNCTION
  * RESERVATION_EXPIRY_FN

* * *

## Broker Functions

These functions are called by the broker .

  

### Function BKR.Startup&

****

**Declaration**

    
    
    BKR.Startup&(BkrSeqNr&)

****

**Parameters**  

  
BkrSeqNr& | Broker sequence number.  
---|---  
  
**Returns**

Returns 1.

**Description**

This function is called by the broker during startup.  It calls the
BKRStarted& function (via a Tuxedo event) in all running trerate and
trerate_tran servers.  The BkrSeqnr& is the only parameter passed to the
BKRStarted& function.

[Contents]

* * *

### Function TenantEnabled&

****

**Declaration**

    
    
    TenantEnabled&()

****

**Parameters**  

**Returns**

Returns TRUE is the system is tenanted.

**Description**

This function is called by the broker on startup in order to set the way the
DAT cache is opened.

[Contents]

* * *

## Database Functions

### Function biDatabaseConnect&

**Declaration**

    
    
    biDatabaseConnect&()
    biDatabaseConnect&(ConnectString$)

**Parameters**

ConnectString$ | Connection string for database instance.  
---|---  
  
**Description**

The biDatabaseConnect& function is used to connect the rating processes (BKRs,
ENMs, ERTs, EROs, trerodb servers and trerate servers) to the database.  If no
defined value is supplied for ConnectString$ then a connection is established
with the default database instance.

**Return Value**  
  
The number of rating processes to which the command was sent.  An EPM
exception is generated on error.

**Implementation**  
  
The DatabaseConnect& function is invoked in all BKR, trerodb and trerate
processes by posting an event to each relevant process.

[Contents]  

* * *

### Function biDatabaseDisconnect&

**Declaration**

    
    
    biDatabaseDisconnect&()

**Parameters**

None.

**Description**

The biDatabaseDisconnect& function is used to disconnect the rating processes
(BKRs, ENMs, ERTs, EROs and trerates) from the database.  This may be required
in order to perform a hot upgrade of Oracle or to update the table model
without having to shut down the rating processes.

**Return Value**  
  
The number of rating processes to which the command was sent.  An EPM
exception is generated on error.

**Implementation**  
  
The DatabaseDisconnect& function is invoked in all BKR and trerate processes
by posting an event to each relevant process.

[Contents]  

* * *

### Function biBkrDatabaseConnect&

**Declaration**

    
    
    biBkrDatabaseConnect&(BkrSeqNr&, ConnectString$, ReprocessInd&)

**Parameters**

BkrSeqNr& | Sequence number of the specific event broker that is to be connected to the database. An undefined (null&) value will attempt to connect all event brokers  
---|---  
ConnectString$ | Connection string for database instance.  
ReprocessInd& | If set to TRUE (1), reprocesses error events that failed due to a database disconnection since the last disconnection of the broker specified.  
  
**Description**

Performs a database connection on the specified broker.

If the reprocess indicator is specified, those (error) events caused by the
latest database disconnection are auto reprocessed

**Return Value**  
  
The number of event broker processes to which the command was sent.  An EPM
exception is generated on error.

**Implementation**  
  

The biBkrDatabaseConnect&() function posts a database connect Tuxedo event to
the broker process(es) to allow a planned switch from non-database mode.
Brokers that receive this post will issue a DatabaseConnect message to any
processes attached to that broker's event cache (ENM, ERO, ERT/trerate).

If the ReprocessInd& is set to TRUE (1) and a single broker is connected
(BkrSeqNr& is defined), a one off task of type 'Reprocess Error Events' is
created if:  
a. The current event files have been closed off (to allow reprocessing).  
b. ERB statistics report the database is on.  
c. ERB statistics report the last database off date is not after the last
database on date.  

If event reprocessing is possible, only events with specific database errors
(assumed to have occurred because of the database disconnection) will be
eligible for reprocessing.

[Contents]  

* * *

### Function biBkrDatabaseDisconnect&

**Declaration**

    
    
    biBkrDatabaseDisconnect&()
    
    
    biBkrDatabaseDisconnect&(BkrSeqNr&)

**Parameters**

BkrSeqNr& | Sequence number of the specific Bkr that is to be disconnected from the database.  
---|---  
  
**Description**

The biBkrDatabaseDisconnect& function is used to disconnect broker processes
(and their associated rating processes) from the database. Specifying a bkr
sequence number as a parameter will only disconnect that specific bkr from the
database.

**Return Value**  
  
The number of bkr processes to which the command was sent.  An EPM exception
is generated on error.

**Implementation**  
  

The biBkrDatabaseDisconnect&() function posts a database disconnect Tuxedo
event to the broker processes to allow a planned switch to non-database mode.
Bkrs that receive this post will issue a DatabaseDisconnect message to any
processes attached to that bkrs event cache (ENM, ERO, ERT).

[Contents]

--------------------------------------------------
## Contents

    Related Documents
    Overview
    Configuration Details
    

Tuxedo Server

    Services
    Tuxedo Service Functions
    EPM Functions
    Initialisation

    Starting the BGP Server
    Server Boot Time
    Pre-processing initialisation.
    Loading Variables
    Variable Evaluation Order
    Modes of Operation
    Context Processing

    Overview
    Message from Higher Context
    Entity Details
    Hierarchy Passes
    Variable Values Passed Between Contexts
    Accumulating Variable Values From Lower Contexts
    Variable Evaluation
    Message to Higher Context
    Customer Context Processing
    Customer Node Context Processing
    Charge Context Processing
    Quality Assurance Bill Runs
    Interim Bill Runs
    

Selecting Charges for Invoicing

    Normalised Event Table SQL Join
    Charge Partitions
    Usage Before Bill Date
    Rental Charges
    Excluding Usage
    Disputed Charges
    

Invoice Generation

    Pending Consolidation
    Variable Purging and Reloading
    Variable Evaluation

    Subtotal Evaluation  
Tariff Evaluation  
Sending Charges to Other Accounts

    Tariffs

    Charge Categories  
Accounts  
GL Codes  
Account Class Codes  
Invoice Text  
Prioritisation

    Special Direct Variables
    Associated Companion Products
    Multiple Processes

    Server Processes  
Inter-Process Communications  
BGP Parent Process  
Customer Node Child Process  
Service Child Process  
Event Child Process  
Multiple Hierarchy Passes  
Parallel Processing

    Statistics
    Commit Points
    Multiple Currencies  
CB 6.00 Partitioning Changes

    Signals
    Financial Reporting Capabilities

    Overview
    GL Codes

    Simple GL Code Allocation
    CB 6.01 GL Guidance

    GL Guidance Function
    Implementation
    Example
    Receivable Types

    Simple Split Receivables

    Receivable Types and Non Billable Charges
    Receivable Type Aggregation
    Rules For Receivable Types
    CB 6.01 Receivable Types

    Invoice Receivable Type Tables
    Example
    Corrective Rounding
    Large Customer Hierarchies
    

    Store Service Details to Disk  
Exclude Idle Services

* * *

## Related Documents

    Detailed Design Document for the BGP  
Variable Evaluation Ordering (VEO) SAS

          _Licence Module SAS_
    Unit Test Plan for the BGP

* * *

## Overview

The Bill Generation Process (BGP) retrieves and accumulates charges generated
by the event rater process (ERT) for the accounts associated with customers on
a particular invoice cycle (identified by a schedule). The BGP itself can also
generate charges by applying billing tariffs. All billable charges are
accumulated to obtain the invoice or statement amount for each account. The
BGP also calculates subtotal values which can be used by other expressions in
the BGP or by the Invoice Generation Process (IGP) by way of the CHARGE table.

The BGP is implemented as a tuxedo server which takes a root customer, or list
of root customers, and generates an invoice record for each customer according
to the date specified. Depending on the server's configuration item it may
spawn other bgp processes which run as tuxedo clients.

Also, depending on which function is called in the server, the BGP will run in
one of four modes of operation. These modes are; "real", "QA", "ExplainPlan"
or "Interim".

Return to contents.

* * *

## Configuration Details

The configuration attributes in the following table exist in the database for
each BGP Server process (the configuration item type is `BGP`).

Attribute Name | Description | Default Value  
---|---|---  
CUSTOMER_CHILD_PROCESSES | The number of customer level child processes that the BGP Server will create. | 0  
NODE_CHILD_PROCESSES | The number of customer node level child processes that the BGP Server will create. A value greater than zero implies a CUSTOMER_CHILD_PROCESSES value of at least 1. | 0  
SERVICE_CHILD_PROCESSES | The number of service level child processes that the BGP Server will create. A value greater than zero implies a CUSTOMER_CHILD_PROCESSES value of at least 1. | 0  
EVENT_CHILD_PROCESSES | The number of child processes that the BGP Server will create when required to process a single service. This attribute should only be set for bill runs that contain high volume services ie. call centres. Values for this attribute must be greater than one, a value of 1 is treated as if it were 0. A value greater than 1 implies a CUSTOMER_CHILD_PROCESSES value of at least 1.Event level processes are only spawned if they are required to process a service during the bill run. | 0  
SERVICE_MIN_EVENTS | The minimum number of events that a service must contain in order to be processed by sub service processes. If this threshold is not exceeded then the service is processed by the context that has spawned sub service processes (CUSTOMER, NODE or SERVICE). | 100000  
EVENT_PERIOD | Number of units of EVENT_PERIOD_TYPE. This determines the date range for which each sub service process will read events and charges from the database for processing. | 1  
EVENT_PERIOD_TYPE | The type of EVENT_PERIOD. This is a drop down list of the available types. Choices are hours or days. | Day  
NON_GLOBAL_DA_CACHE_SIZE | The size of the cache of derived attributes with a storage context of service or customer node. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" eg. 100M then the cache's size is the number of mega bytes that the cache is able to consume. | 100  
GLOBAL_DA_CACHE_SIZE | The size of the cache of derived attributes with a storage context of global. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" eg. 100M then the cache's size is the number of mega bytes that the cache is able to consume. | Unlimited  
DEBUG_LEVEL | This attribute sets the inital BGP tracing level. The tracing level may be changed at runtime using the biTrcBGP& function. Debug levels supported by BGP are:  
0x0000 (OFF) = Turns tracing off.  
0x0001 (MEM) = generates a memory usage report on exit.  
0x00002 (ORA) = Oracle tracing.  
0x00004 (RDB) = Database interaction tracing (SQL tracing is enabled along
with this level).  
0x00008 (CHG) = charge details.  
0x00010 (EVT) = normalised event details.  
0x00020 (SER) = service details.  
0x00040 (EPM) = EPM details.  
0x00080 (ACC) = account details.  
0x00100 (NOD) = node details.  
0x00200 (CUS) = customer details.  
0x00400 (VAR) = variable tracing.  
0x00800 (VEO) = variable evaluation order tracing.  
0x01000 (PHA) = process phase tracing.  
0x02000 (MSG) = context message tracing.  
0x04000 (MUL) = multi-process tracing.  
0x08000 (DBG) = debug messages.  
0x10000 (GL) = GL tracing (GLAudit)  
0x20000 (EPM_LIGHT) = EPM details excluding function call parameter and return
details.  
0x40000 (SQL) = SQL Connection and cursor operations details (RDB tracingis
enabled along with this level).  
 Multiple trace levels can be defined by specifying the mnemonics in a comma separated list. Example: VEO,VAR will enable variable and variable evaluation order tracing. A trace level that evaluates to zero will turn tracing off. Tracing is written to the file bgp.trc.trebgp.<processid>.yyyymmddhhmmss in the $ATA_DATA_SERVER_LOG directory. This applies to both parent and child processes.  **NOTE:** To turn off SQL/RDB tracing, make sure none of them is specified in the new debug levels.  | No tracing.  
ERROR_THRESHOLD | The maximum number of customer hierarchies that can be in error for a given call before aborting the bill run. A value of NULL or 0 is equivalent to no error threshold, which allows for an unlimited number of errors. | NULL (No Error Threshold)  
USAGE_CHARGES_BEFORE_BILL_DATE | If set to TRUE, the BGP will process usage charges prior to but not including the bill run effective date.  If set to FALSE, the BGP will process usage charges prior to and including the bill run effective date. For example, consider a bill run with an effective date of 04-AUG-2004 10:00:00.  If set to TRUE, usage charge will be processed up to and including 04-AUG-2004 9:59:59.  If set to FALSE, usage charges on 04-AUG-2004 10:00:00 will also be processed. The EVENT_CLASS_CODE column in the NORMALISED_EVENT table is not used by the BGP to distinguish usage events from rental events. An event is considered to be a usage event if the BILL_RUN_ID column in the NORMALISED_EVENT table is NULL.  All events generated by the Rental Generation Process (RGP) have the BILL_RUN_ID populated and are therefore not considered to be usage events. Rental charges will be processed up to and including the effective date of the bill run regardless of the value of this attribute.  | FALSE.  
STATISTICS_TIMEOUT | Specifies how frequently the BGP and its associated child processes log their statistics in the TRE Monitor while the BGP is active. This value specifies the number of seconds between each successive call to STATISTICS_FUNCTION. Statistics are also logged on commencement and completion of each biInvoiceGenerate& call.  If not specified, statistics are not logged in the TRE Monitor.  | No logging of statistics  
STATISTICS_FUNCTION | The name of the function that is called every STATISTICS_TIMEOUT seconds from the BGP parent and children processes.The default STATISTICS_FUNCTION is BGPLogStatistics&() | BGPLogStatistics&()  
VARIABLE_CACHE_SIZE | The size of each of the BGP's variable caches. The BGP has two caches to store variable pass orders.  If specified as a positive number the cache's size is the number of variable pass orders that can be stored. If specified as a number with a trailing "M" eg. 100M then the cache's size is the number of mega bytes that the cache is able to consume. | 50M  
SERVICE_DETAILS_TO_DISK | Determines if service details are written to disk at the end of each service pass. If set to TRUE, at the end of a service pass service details are written to disk and removed from memory, reducing the amount of memory required to process the customer hierarchy.If set to false (the default) all service details are cached in memory until the customer has finished being processed. See Large Customer Hierarchies for more information | FALSE  
DISABLE_TRANSFER_CHARGES | Determines if the BGP is to ignore transfer charges when generating the variable evaluation order for a customer.Transfer charges are charges generated by a service that is not directly associated with the account to which the charge is directed.  This option gives a performance improvement for hierarchies with high volumes of charges as it makes it unnecessary to query the charge table when retrieving the list of services associated with a customer.  This list of services is required to generate the variable evaluation order for a customer. This option should only be used if it can be guaranteed that all charges generated for all services on each hierarchy are always directed to accounts directly associated with each service's owning customer node. That is, there is no use of intra-hierarchy or inter-hierarchy transfer charges during rating or billing. | FALSE  
ENABLE_QA_TRANSFER_CHARGES | Controls the BGP's behaviour with regard to inter-hierarchy transfer charges generated during Quality Assurance bill runs.If set to FALSE (the default) then inter-hierarchy transfer charges are suppressed during QA bill runs.If set to TRUE then inter-hierarchy transfer charges are generated normally during QA bill runs, and special filtering and handling of charges is performed during QA and non-QA bill runs. See Quality Assurance Bill Runs for more information.There is a minor performance overhead if this attribute is enabled. | FALSE  
EXCLUDE_IDLE_SERVICES | Determines if the BGP is to automatically exclude services that have no unbilled charges for the current billing period.This option reduces the amount of memory required to process a large hierarchy See Large Customer Hierarchies for more information | FALSE  
EXCLUDE_QA_USAGE | Controls the BGP's behaviour with regard to processing usage charges during quality assurance bill runs. If set to true (1) then usage charges are excluded from processing and will not be included in invoice totals nor appear on QA invoices. If set to false (0) then usages charges are processed and included in QA invoices. This attribute only affects quality assurance bill runs, standard bill runs are unaffected. See Quality Assurance Bill Runs for more information.| FALSE  
DISABLE_PARALLEL_QUERY_HINT | When the BGP is configured for multi-processing, various queries include the PARALLEL_INDEX hint, where the degree parameter is equal to the total number of BGP child processes configured under the current process. When many entities (e.g Customer Nodes or Services) exist without any associated charges, the overhead of using parallel servers may negate the performance benefits.   
  
This configuration option can be used to disable the inclusion of this hint.
The setting affects all BGP queries.| FALSE  
LOG_BGP_PASSES | Determines whether the BGP process will write a message to the $ATA_DATA_SERVER_LOG/log.out file at the beginning of each hierarchy pass for every customer it processes.  
SERVICES_PER_NODE_THRESHOLD | (Added 11.00.20.01) The maximum number of services per customer node for which queries on the CHARGE table should continue to use the I_CHARGE_ACCOUNT or I_CHARGE_INVOICE index in conjunction with the I_CHARGE_SERVICE index. Performance testing has indicated that billing performance can be improved significantly for deployments with large numbers of services per customer node if the query on the CHARGE table does not use the I_CHARGE_ACCOUNT or I_CHARGE_INVOICE indexes and instead just uses the I_CHARGE_SERVICE index. By default this attribute is undefined. If it is undefined or has a value of 0 then then maximum value is unlimited and the I_CHARGE_ACCOUNT and/or I_CHARGE_INVOICE indexes will always be used. The attribute is only considered if the BGP is configured with SERVICE_CHILD_PROCESSES > 0 and/or EVENT_CHILD_PROCESSES > 0. For deployments with a large number of services per customer node wishing to test the performance benefits of this new attribute, an initial value of 1000 is recommended.  
  
Return to contents.

* * *

# BGP Server

## Services

  * **biBGP**  
This service performs all processing and management of bill runs. It
implements the following functions:

    * biInvoiceGenerate&
    * biInvoiceGenerateCorporate&
    * biInvoiceGenerateHighVolume&
    * biInvoiceExplainPlan$
    * biGLNormalisedEventFileAudit&
    * biGLInvoiceAudit&
  

  * **biQuoteBGP**  
This service performs processing of bill runs in quote mode. It implements the
biQuoteInvoiceGenerate& function that is intended for quoting purposes only.

## Tuxedo Service Functions

The following functions are handled by the BGP:

biInvoiceGenerate& | biInvoiceGenerate& (Interim Mode)  
---|---  
biInvoiceGenerateCorporate& | biInvoiceGenerateCorporate& (Interim Mode)  
biInvoiceGenerateHighVolume& | biInvoiceGenerateHighVolume& (Interim Mode)  
biInvoiceExplainPlan$ | InvoiceExplainPlan$;  
biQuoteInvoiceGenerate& | InvoiceGenerate&  
  
### Function biInvoiceGenerate&

#### Declaration

biInvoiceGenerate&(BillRunId&,  
                   EffectiveDate~,  
                   BillRunOperationId&,  
                   QAInd&,  
                   RootCustomerNodeList&[],  
                   var SuccessCustomerNodeList&[],  
                   var ErrorCustomerNodeList&[],  
                   var SuppressedCustomerNodeList&[],  
                   var OperationStatistics?{})

biInvoiceGenerateCorporate&(BillRunId&,  
                            EffectiveDate~,  
                            BillRunOperationId&,  
                            QAInd&,  
                            RootCustomerNodeList&[],  
                            var SuccessCustomerNodeList&[],  
                            var ErrorCustomerNodeList&[],  
                            var SuppressedCustomerNodeList&[],   
                            var OperationStatistics?{}) 

biInvoiceGenerateHighVolume&(BillRunId&,  
                             EffectiveDate~,  
                             BillRunOperationId&,  
                             QAInd&,  
                             RootCustomerNodeList&[],  
                             var SuccessCustomerNodeList&[],  
                             var ErrorCustomerNodeList&[],  
                             var SuppressedCustomerNodeList&[],  
                             var OperationStatistics?{}) 

#### Parameters

BillRunId& | The id of the bill run being processed.  
---|---  
EffectiveDate~ | The effective date of the bill run.  
BillRunOperationId& | The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
QAInd& | Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run  
RootCustomerNodeList&[] | The list of root customer nodes which the BGP server must process. The list will contain a single entry in the case of an on-demand bill run. The list may not be empty.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling program. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server returned to the calling program.  
var SuppressedCustomerNodeList&[] | A list of root customer ids that have had their invoices suppressed returned to the calling program. Invoices are suppressed by the invoice type expressions on the invoice type. Invoices will only be suppressed for a hierarchy if ALL invoices in the hierarchy are suppressed. Note that child customer nodes with a report level other than "Invoice" are excluded from this condition.It should be noted that there is no specific invoice suppression expression on the invoice type. Rather, invoice type expressions are able to set the direct variable associated with the SUPPRESS_IND_CODE column in the INVOICE table.  
var OperationStatistics?{} | Unknown EPM hash returned to the caller containing the statistics gathered during the processing of the list of root customers. The statistics structure contains:

  1. Key: TotalCharges  
The number of original charges that are processed by the bill run.

  2. Key: TotalEvents  
The number of original normalised events that are processed by the bill run.

  3. Key: TotalServices  
The number of services that are processed by the bill run.

  4. Key: ExcludedServices  
The number of services that were eligible to be processed but were excluded
due them having no usage or rental charges associated with them.   This key
can only contain a non-zero value if the EXCLUDE_IDLE_SERVICES configuration
attribute is set to TRUE.

  5. Key: TotalCustomerNodes  
The number of customer nodes that are processed by the bill run.

  6. Key: MaxChargePasses  
The maximum number of passes to NE/CHARGE context for this bill run.

  7. Key: MinChargePasses  
The minimum number of passes to NE/CHARGE context for this bill run.

  8. Key: TariffChargesGenerated  
Total number of tariff charges generated for the bill run.

  9. Key: SubtotalChargesGenerated  
Total number of subtotal charges generated for the bill run.

  10. Key: Invoices  
Total number of invoices generated for this bill run.

  11. Key: Statements  
Total number of invoice records generated for statements on this bill run.
This includes invoice records for secondary accounts, invoice records for the
primary accounts of non-reporting customer nodes (ie. those for which no
statement image will be generated), and invoice records that have been
converted to statements pending consolidation.

  12. Key: PendingConsolidation  
Total number of invoice records converted to statements pending consolidation.
These statements are included in the total for the Statements statistics.

  13. Key: InvoiceAmount  
Sum total of the invoiced amount generated by the bill run.

  14. Key: StatementAmount  
Sum total of the statement amount generated by the bill run.

  
  
#### Returns

TRUE if the bill run was successful. If unsuccessful, a Tuxedo error is raised
by calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

These are wrappers function, please see  InvoiceGenerate&.

biInvoiceGenerateCorporate& and biInvoiceGenerateHighVolume& functions can be
used for Corporate and High Volume Customers respectively. The only difference
with biInvoiceGenerate&() is the remote service names being used in these
functions. The  biInvoiceGenerateCorporate& has been implemented with
biBGPCorporate as remote service name and biInvoiceGenerateHighVolume&  with
biBGPHighVol as remote service name. This to  allow Corporate/High Volume
customers to be directed to their own own set of bgp servers  which may have a
different configuration more suited to the processing of large Corporate/High
Volume hierarchies.

[Tuxedo Service Functions] [Contents]

* * *

### Function biInvoiceGenerate& (Interim Mode)

biInvoiceGenerate& is overloaded to allow support for interim invoicing mode.
When generating interim invoices, biInvoiceGenerate& is called with an extra
parameter InterimInd& which is a boolean flag indicating whether or not the
BGP should operate in interim mode.

#### Declaration

biInvoiceGenerate&(BillRunId&,  
                   EffectiveDate~,  
                   BillRunOperationId&,  
                   QAInd&,  
                   InterimInd&,  
                   RootCustomerNodeList&[],  
                   var SuccessCustomerNodeList&[],  
                   var ErrorCustomerNodeList&[],  
                   var SuppressedCustomerNodeList&[],  
                   var OperationStatistics?{})

biInvoiceGenerateCorporate&(BillRunId&,  
                            EffectiveDate~,  
                            BillRunOperationId&,  
                            QAInd&,  
                            InterimInd&,  
                            RootCustomerNodeList&[],  
                            var SuccessCustomerNodeList&[],  
                            var ErrorCustomerNodeList&[],  
                            var SuppressedCustomerNodeList&[],  
                            var OperationStatistics?{})

biInvoiceGenerateHighVolume&(BillRunId&,  
                             EffectiveDate~,  
                             BillRunOperationId&,  
                             QAInd&,  
                             InterimInd&,  
                             RootCustomerNodeList&[],  
                             var SuccessCustomerNodeList&[],  
                             var ErrorCustomerNodeList&[],  
                             var SuppressedCustomerNodeList&[],  
                             var OperationStatistics?{})

#### Parameters

BillRunId& | The id of the bill run being processed.  
---|---  
EffectiveDate~ | The effective date of the bill run.  
BillRunOperationId& | The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
QAInd& | Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run  
InterimInd& | Indicates whether or not the BGP should operate in interim mode for the duration of the bill run. TRUE indicates an interim bill run.  
RootCustomerNodeList&[] | The list of root customer nodes which the BGP server must process. The list will contain a single entry in the case of an on-demand bill run. The list may not be empty.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling program. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server returned to the calling program.  
var SuppressedCustomerNodeList&[] | A list of root customer ids that have had their invoices suppressed returned to the calling program. Invoices are suppressed by the invoice type expressions on the invoice type. Invoices will only be suppressed for a hierarchy if ALL invoices in the hierarchy are suppressed.It should be noted that there is no specific invoice suppression expression on the invoice type. Rather, invoice type expressions are able to set the direct variable associated with the SUPPRESS_IND_CODE column in the INVOICE table.  
var OperationStatistics?{} | Unknown EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers. The statistics structure contains:

  1. Key: TotalCharges  
The number of original charges that are processed by the bill run.

  2. Key: TotalEvents  
The number of original normalised events that are processed by the bill run.

  3. Key: TotalServices  
The number of services that are processed by the bill run.

  4. Key: ExcludedServices  
The number of services that were eligible to be processed but were excluded
due them having no usage or rental charges associated with them.   This key
can only contain a non-zero value if the EXCLUDE_IDLE_SERVICES configuration
attribute is set to TRUE.

  5. Key: TotalCustomerNodes  
The number of customer nodes that are processed by the bill run.

  6. Key: MaxChargePasses  
The maximum number of passes to NE/CHARGE context for this bill run.

  7. Key: MinChargePasses  
The minimum number of passes to NE/CHARGE context for this bill run.

  8. Key: TariffChargesGenerated  
Total number of tariff charges generated for the bill run.

  9. Key: SubtotalChargesGenerated  
Total number of subtotal charges generated for the bill run.

  10. Key: Invoices  
Total number of invoices generated for this bill run.

  11. Key: Statements  
Total number of invoice records generated for statements on this bill run.
This includes invoice records for secondary accounts, invoice records for the
primary accounts of non-reporting customer nodes (ie. those for which no
statement image will be generated), and invoice records that have been
converted to statements pending consolidation.

  12. Key: PendingConsolidation  
Total number of invoice records converted to statements pending consolidation.
These statements are included in the total for the Statements statistics.

  13. Key: InvoiceAmount  
Sum total of the invoiced amount generated by the bill run.

  14. Key: StatementAmount  
Sum total of the statement amount generated by the bill run.

  
  
#### Returns

TRUE if the bill run was successful. If unsuccessful, a Tuxedo error is raised
by calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

The implementation of this function is almost identical to biInvoiceGenerate&
except that the BGP operates in interim mode.

The biInvoiceGenerateCorporate& (Interim Mode) and
biInvoiceGenerateHighVolume& (Interim Mode) are wrappers around
InvoiceGenerate& function where BGP operates in interim mode.

[Tuxedo Service Functions] [Contents]

* * *

### Function biQuoteInvoiceGenerate&

#### Declaration

biQuoteInvoiceGenerate&(BillRunId&,  
                   EffectiveDate~,  
                   BillRunOperationId&,  
                   QAInd&,  
                   RootCustomerNodeList&[],  
                   var SuccessCustomerNodeList&[],  
                   var ErrorCustomerNodeList&[],  
                   var SuppressedCustomerNodeList&[],  
                   var Statistics?{})

BillRunId& | The id of the bill run being processed.  
---|---  
EffectiveDate~ | The effective date of the bill run.  
BillRunOperationId& | The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
QAInd& | Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run  
RootCustomerNodeList&[] | The list of root customer nodes which the BGP server must process. The list will contain a single entry in the case of an on-demand bill run. The list may not be empty.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling program. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server returned to the calling program.  
var SuppressedCustomerNodeList&[] | A list of root customer ids that have had their invoices suppressed returned to the calling program. Invoices are suppressed by the invoice type expressions on the invoice type. Invoices will only be suppressed for a hierarchy if ALL invoices in the hierarchy are suppressed. Note that child customer nodes with a report level other than "Invoice" are excluded from this condition.It should be noted that there is no specific invoice suppression expression on the invoice type. Rather, invoice type expressions are able to set the direct variable associated with the SUPPRESS_IND_CODE column in the INVOICE table.  
var Statistics?{} | Unknown EPM hash returned to the caller containing the statistics gathered during the processing of the list of root customers. The statistics structure contains:

  1. Key: TotalCharges  
The number of original charges that are processed by the bill run.

  2. Key: TotalEvents  
The number of original normalised events that are processed by the bill run.

  3. Key: TotalServices  
The number of services that are processed by the bill run.

  4. Key: ExcludedServices  
The number of services that were eligible to be processed but were excluded
due them having no usage or rental charges associated with them.   This key
can only contain a non-zero value if the EXCLUDE_IDLE_SERVICES configuration
attribute is set to TRUE.

  5. Key: TotalCustomerNodes  
The number of customer nodes that are processed by the bill run.

  6. Key: MaxChargePasses  
The maximum number of passes to NE/CHARGE context for this bill run.

  7. Key: MinChargePasses  
The minimum number of passes to NE/CHARGE context for this bill run.

  8. Key: TariffChargesGenerated  
Total number of tariff charges generated for the bill run.

  9. Key: SubtotalChargesGenerated  
Total number of subtotal charges generated for the bill run.

  10. Key: Invoices  
Total number of invoices generated for this bill run.

  11. Key: Statements  
Total number of invoice records generated for statements on this bill run.
This includes invoice records for secondary accounts, invoice records for the
primary accounts of non-reporting customer nodes (ie. those for which no
statement image will be generated), and invoice records that have been
converted to statements pending consolidation.

  12. Key: PendingConsolidation  
Total number of invoice records converted to statements pending consolidation.
These statements are included in the total for the Statements statistics.

  13. Key: InvoiceAmount  
Sum total of the invoiced amount generated by the bill run.

  14. Key: StatementAmount  
Sum total of the statement amount generated by the bill run.

  
  
#### Returns

TRUE if the bill run was successful. If unsuccessful, a Tuxedo error is raised
by calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

The implementation of this function is almost identical to
biInvoiceGenerate&. The only difference with biInvoiceGenerate& is the remote
service name being used.

* * *

### Function biInvoiceExplainPlan$

#### Declaration

biInvoiceExplainPlan$(EffectiveDate~,  
                      RootCustomerNode&)

#### Parameters

EffectiveDate~ | The date for which the explanation is given.  
---|---  
RootCustomerNode& | The root customer node id for which the explanation is given.  
  
#### Returns

A string containing the explanation of the execution plan for the customer
specified at the date specified. If unsuccessful, a Tuxedo error is raised by
calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

This is a wrapper function, please see InvoiceExplainPlan$.

#### Usage

Unlike biInvoiceGenerate&(...), this function will not be called by the
billing controller. Instead, it will either be called directly by an external
program or as part of an immediate task.

[Tuxedo Service Functions] [Contents]

* * *

### Function InvoiceGenerate&

#### Declaration

InvoiceGenerate&(BillRunId&,  
                 EffectiveDate~,  
                 BillRunOperationId&,  
                 QAInd&,  
                 InterimInd&,  
                 RootCustomerNodeList&[],  
                 var SuccessCustomerNodeList&[],  
                 var ErrorCustomerNodeList&[],  
                 var SuppressedCustomerNodeList&[],  
                 var OperationStatistics?{})

#### Parameters

BillRunId& | The id of the bill run being processed.  
---|---  
EffectiveDate~ | The effective date of the bill run.  
BillRunOperationId& | The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
QAInd& | Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run  
InterimInd& | Indicates whether or not the BGP should operate in interim mode for the duration of the bill run. TRUE indicates an interim bill run.  
RootCustomerNodeList&[] | The list of root customer nodes which the BGP server must process. The list will contain a single entry in the case of an on-demand bill run. The list may not be empty.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling program. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server returned to the calling program.  
var SuppressedCustomerNodeList&[] | A list of root customer ids that have had their invoices suppressed returned to the calling program. Invoices are suppressed by the invoice type expressions on the invoice type. Invoices will only be suppressed for a hierarchy if ALL invoices in the hierarchy are suppressed.It should be noted that there is no specific invoice suppression expression on the invoice type. Rather, invoice type expressions are able to set the direct variable associated with the SUPPRESS_IND_CODE column in the INVOICE table.  
var OperationStatistics?{} | Unknown EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers. The statistics structure contains:

  1. Key: TotalCharges  
The number of original charges that are processed by the bill run.

  2. Key: TotalEvents  
The number of original normalised events that are processed by the bill run.

  3. Key: TotalServices  
The number of services that are processed by the bill run.

  4. Key: ExcludedServices  
The number of services that were eligible to be processed but were excluded
due them having no usage or rental charges associated with them. This key can
only contain a non-zero value if the  EXCLUDE_IDLE_SERVICES configuration
attribute is set to TRUE.

  5. Key: TotalCustomerNodes  
The number of customer nodes that are processed by the bill run.

  6. Key: MaxChargePasses  
The maximum number of passes to NE/CHARGE context for this bill run.

  7. Key: MinChargePasses  
The minimum number of passes to NE/CHARGE context for this bill run.

  8. Key: TariffChargesGenerated  
Total number of tariff charges generated for the bill run.

  9. Key: SubtotalChargesGenerated  
Total number of subtotal charges generated for the bill run.

  10. Key: Invoices  
Total number of invoices generated for this bill run.

  11. Key: Statements  
Total number of invoice records generated for statements on this bill run.
This includes invoice records for secondary accounts, invoice records for the
primary accounts of non-reporting customer nodes (ie. those for which no
statement image will be generated), and invoice records that have been
converted to statements pending consolidation.

  12. Key: PendingConsolidation  
Total number of invoice records converted to statements pending consolidation.
These statements are included in the total for the Statements statistics.

  13. Key: InvoiceAmount  
Sum total of the invoiced amount generated by the bill run.

  14. Key: StatementAmount  
Sum total of the statement amount generated by the bill run.

  
  
#### Returns

TRUE if the bill run was successful. If unsuccessful, a Tuxedo error is raised
by calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

InvoiceGenerate& takes an ordered list of root customer node ids from the
billing controller and then generates a bill for each customer in turn at the
effective date specified. This function is responsible for applying and
releasing locks on customers and for managing the server's error threshold. It
is also responsible for supplying the calling program with lists of
successful, erred, and suppressed customers. See the parameter explanation
above for further details.

A bill run will be unsuccessful if any of the following conditions occur:

  1. The BGP Server's error threshold is exceeded.
  2. A detectable error occurs that is fatal to the BGP Server.
  3. An error is detected by the BGP Server with the parameters in the call to InvoiceGenerate&

In the case that the BGP Server has an unforseen fatal error ie. core dump and
is unable to return from the call to InvoiceGenerate&, it is the billing
controller's responsibility to terminate the bill run gracefully.

Customers marked as suppressed are left in a "Running" status in the
CUSTOMER_NODE_BILL_RUN table for the current bill run operation Id. It is the
responsibility of the billing configuration compliant wrapper (e.g
biBillRunInvoiceGenerate&) to revoke the invoice, revoke the rental events and
update the CUSTOMER_NODE_BILL_RUN status to "Suppressed" for each customer.

#### Licence check

Before InvoiceGenerate& processes a root customer, confirm checking of licence
entity status will be performed every 24 hours (base on billing request) to
ensure the current licence information is correct. Fail to check licence
information or the incorrect licence information will cause InvoiceGenerate&
failure.

#### Customer Locking

Before InvoiceGenerate& processes a root customer it must obtain a lock on the
customer to prevent any other billing operation from interfering with it's
processing. Locks are obtained by updating the CUSTOMER_NODE table with the
BGP Servers bill run operation id and process id. If these fields are NULL a
lock is obtained. After the customer has been processed, the lock is released
to other billing processes.

InvoiceGenerate& obtains, and commits to the database, locks on all customers
before the first customer is processed.  These locks are released after the
last customer has been processed. If a lock is not obtained for a customer
then that customer is immediately placed into the erred customer list and is
not processed.

[Tuxedo Service Functions] [Contents]

* * *

### Function InvoiceExplainPlan$

#### Declaration

InvoiceExplainPlan$(EffectiveDate~,  
                    RootCustomerNode&)

#### Parameters

EffectiveDate~ | The date for which the explanation is given.  
---|---  
RootCustomerNode& | The root customer node id for which the explanation is given.  
  
#### Returns

A string containing the explanation of the execution plan for the customer
specified at the date specified. If unsuccessful, a Tuxedo error is raised by
calling tpreturn with TPFAIL and an application return code parameter
indicating the reason for the failure.

#### Description

The explanation provides information on the following aspects of the bill run:

  1. The number of passes to the CHARGE / NORMALISED_EVENT contexts that will occur while processing the customer. 
  2. An ordered list of all variables (and their contexts) that will be evaluated.
  3. Any cases where a variable will cause the multi-processing capability of the BGP Server to run sequentially. Two types of variables can affect the BGP's ability to process entities in parallel :-

Progressive subtotals

A progressive subtotal (or running subtotal) is one that can be referenced
before its final value is calculated. For more information see Subtotal
Evaluation or the Detailed Design Document. It follows that there can only be
one value of the subtotal at any one time and any variables that reference the
subtotal cannot be processed in parallel. If a progressive subtotal is
affecting the evaluation order a message such as this will appear in the
explain plan :-



` <M12012> Variables 13 to 24 are processed sequentially because the range
includes variables that depend on progressive subtotal sProgressiveSubtotal&.`

  
The range of variables at the start of the message indicates the full pass
that contains the reference to the progressive subtotal. For example if the
message appears in the "Parallel processing at the Service context" section
then the variables represent an entire pass to the service context. Just one
reference to the progressive subtotal will cause the entire range to be
processed sequentially. The variables that reference the progressive subtotal
(either directly or indirectly) are not output in the explain plan however
they are output to a BGP tracefile with "PHA" (phase) level tracing enabled.

Aggregate subtotals

An aggregate subtotal is one at the customer node context that includes the
value of the subtotal of its child nodes. For more information see Subtotal
Evaluation or the Detailed Design Document. Aggregate subtotals create the
requirement that a node cannot be processed until all of its child nodes have
been processed. This can limit the number of nodes that are processed in
parallel. If aggregate subtotals are affecting evaluation then a message such
as this will appear in the explain plan

`<M12014> Variables 13 to 29 are processed by all child nodes before being
processed by the parent node because variable 14 is an aggregation subtotal.`

The variable range represents the entire pass to the customer node context
where the subtotal is evaluated

. It is only the pass where the subtotal itself is evaluated that is affected.
The evaluation of subtotal terms is not affected.

  4. Any forced passes to CUSTOMER caused by intra-hierarchy tariffs.
  5. Any case of a progressive subtotal that is not progressive due to the variable evaluation order.

If the call to InvoiceExplainPlan$ fails a Tuxedo error is raised by calling
tpreturn with TPFAIL and with an application return code parameter indicating
the reason for the failure. The call will be unsuccessful under the following
conditions:

  1. A detectable error occurs that is fatal to the BGP Server.
  2. An error is detected by the BGP Server with the parameters in the call to InvoiceExplainPlan$.

#### Usage

Unlike InvoiceGenerate&(...), this function will not be called by the billing
controller. Instead, it will either be called directly by an external program
or as part of an immediate task.

[Tuxedo Service Functions] [Contents]

* * *

## EPM Functions

The following functions are registered with the BGP's parser. In addition, the
EPM functions provided by the GLC are also registered.

CurrencyPurge& | DerivedAttributePurge&  
---|---  
DerivedTablePurge& | FunctionPurge&  
InvoiceTypePurge& | ProductPurge&  
ReferenceTypePurge& | ReferenceTypePurgeById&  
ReferenceTypePurgeByLabel& | SubtotalPurge&  
TariffPurge& | BGPStats?{}  
InterimMode& | BGPLogStatistics&  
BGPTrace& | InvoiceAccountInserted&  
ServiceHasProduct& | ServiceHasTariff&  
ServiceProducts$[] | CustomerNodeHasProduct&  
CustomerNodeHasTariff& | CustomerHasProduct&  
CustomerHasTariff& | BillRunId&  
GetCurrencySymbol$ | LoggerReload&  
SubtotalName$ |    
  
The following function are implemented in EPM for use in the BGP server:

    BGPLogStatistics&  
    BGP.BypassEventQueryMode&  
    BilledProportion#  
    BilledCharge#  
    TariffType&  
    TariffName$

* * *

### Function CurrencyPurge&

#### Declaration

CurrencyPurge&(CurrencyId&)

#### Paramenters

CurrencyId& | The Currency Id to purge from the CCM.  
---|---  
  
**Description**

This callback function will remove a currency, and any exchange rates that the
currency participates in, from the BGP's currency cache. The currency is
reloaded by the cache the next time that it is used. See the Ccm SAS for more
details.

[EPM Functions] [Contents]

* * *

### Function DerivedAttributePurge&

#### Declaration

DerivedAttributePurge&(DerivedAttributeId&)

#### Paramenters

DerivedAttributeId& | The id of the derived attribute to purge.  
---|---  
  
#### Description

This callback function purges a derived attribute from the BGP Servers
variable caches. Specifically, the data structures affected by this function
are:

  1. Derived attribute container (DAM) 
  2. Variable evaluation order. 
  3. Variable pass order. 

When a derived attribute is purged it is first removed from the Dam container
and then reloaded. The variable evaluation and pass orders will only need
updating if either the date range of the derived attribute or its dependencies
change.

See the Variable Evaluation Order SAS for more information on derived
attribute purging.

[EPM Functions] [Contents]

* * *

### Function DerivedTablePurge&

**Declaration**

DerivedTablePurge&(TableName$)

**Parameters**

TableName$ | The name of the Derived Table to purge  
---|---  
  
**Description**

This function removes the specified table from the global derived attribute
table cache of the current process. If multiple copies of this table have been
cached for different date ranges, then all copies are removed. It is
implemented using DatGlobalCache::PurgeTable() method in the DAT module.

[EPM Functions] [Contents]

* * *

### Function FunctionPurge&

#### Declaration

FunctionPurge&(FunctionName$)

#### Paramenters

FunctionName$ | The name of the function to purge.  
---|---  
  
#### Description

This callback function will purge and reload the specified function from the
variable evaluation order, variable pass order lists and base parser in the
BGP. Under normal circumstances, purging is only necessary if either the
function's date range or dependencies change. However, if the function's name
or interface changes then all of the BGP's variable caches are flushed for the
date range of the change. This includes:

  1. Base parser. The base parser must be completely reset. 
  2. Variable containers, GTM, DAM, SUB, Direct Variable containers. 
  3. Variable evaluation order. 
  4. Variable pass order. 
  5. Product variable cache. 
  6. Product combination cache. 

A function interface change is detected by removing the function definition
from the base parser and then reloading it. If the reload fails then it is
assumed that the function name and / or interface has changed and the above
action is carried out.

For more information on purging functions see Variable Evaluation Order SAS.

[EPM Functions] [Contents]

* * *

### Function InvoiceTypePurge&

#### Declaration

InvoiceTypePurge&(InvoiceTypeId&)

#### Paramenters

InvoiceTypeId& | The Invoice Type Id to purge from  
---|---  
  
**Description**

This callback function will remove an Invoice Type, from the BGP's Invoice
Type Module (Itm) cache.

[EPM Functions] [Contents]

* * *

### Function ProductPurge&

#### Declaration

ProductPurge&(ProductId&)

#### Paramenters

ProductId& | The product definition id to be purged from the BGP's product caches.  
---|---  
  
#### Description

This callback function will purge and reload a product in the BGP Server's
product caches. Specifically, the caches affected by this function are:

  1. Product combination cache. 
  2. Multi-product combination cache. 
  3. Product variable cache. 

[EPM Functions] [Contents]

* * *

### ReferenceTypePurge&

**Declaration**

ReferenceTypePurge&(ReferenceTypeAbbreviation$)

**Parameters**

ReferenceTypeAbbreviation$ | The abbreviation of the Reference Type to purge  
---|---  
  
**Description**

This function is used to purge the specified reference type (identified by
it's abbreviation) from the global Reference Type cache.

It it implemented using the ReferenceTypeCache::PurgeByAbbrev() method in the
REF module.

[EPM Functions] [Contents]

* * *

### ReferenceTypePurgeById&

**Declaration**

ReferenceTypePurgeById&(ReferenceTypeId&)

**Parameters**

ReferenceTypeId& | The ID of the Reference Type to purge  
---|---  
  
**Description**

This function is used to purge the specified reference type (identified by
it's ID) from the global Reference Type cache.

It it implemented using the ReferenceTypeCache::PurgeById() method in the REF
module.

[EPM Functions] [Contents]

* * *

### ReferenceTypePurgeByLabel&

**Declaration**

ReferenceTypePurgeByLabel&(TypeLabel$)

**Parameters**

TypeLabel$ | The type label of the Reference Type to purge  
---|---  
  
**Description**

This function is used to purge the specified reference type (identified by
it's label) from the global Reference Type cache.

It it implemented using the ReferenceTypeCache::PurgeByLabel() method in the
REF module.

[EPM Functions] [Contents]

* * *

### Function SubtotalPurge&

#### Declaration

SubtotalPurge&(SubtotalId&)

#### Paramenters

SubtotalId& | Id of the subtotal to purge.  
---|---  
  
#### Description

This callback function purges a subtotal and its terms from the BGP Server's
variable caches. Specifically, the data structures affected by this function
are:

  1. Subtotal container (SUB) 
  2. Variable evaluation order. 
  3. Variable pass order. 

When a subtotal is purged it is first removed from the Sub container and then
reloaded. The properties of the subtotal and its terms which have changed are
then inspected to see if the variable evaluation and or pass order need to be
updated. These properties are documented in the variable evaluation order SAS.

See the Variable Evaluation Order SAS for more information on subtotal
purging.

[EPM Functions] [Contents]

* * *

### Function TariffPurge&

#### Declaration

TariffPurge&(TariffId&)

#### Paramenters

TariffId& | The id of the tariff to purge.  
---|---  
  
#### Description

This callback function purges a tariff from the BGP Servers variable caches.
Specifically, the data structures affected by this function are:

  1. Tariff container (GTM) 
  2. Variable evaluation order. 
  3. Variable pass order. 

When a tariff is purged it is first removed from the Gtm container and then
reloaded. The properties of the tariff which have changed are then inspected
to see if the variable evaluation and or pass order need to be updated. These
properties are documented in the variable evaluation order SAS.

See the Variable Evaluation Order SAS for more information on tariff purging.

[EPM Functions] [Contents]

* * *

### Function BGPStats?{}

#### Declaration

BGPStats?{}()

#### Returns

Returns a hash of statistics gathered by the BGP process from which it was
called since its creation.

#### Description

The statistics returned depend on the process from which the function was
called. If called from the parent process, the hash contains statistics
gathered since boot time by the BGP (including any child processes). If called
from a child process, the hash returned includes a subset of the total
statistics, gathered by the particular process from which the function was
called.

If called from the parent process, the function returns a hash containing the
following statistics:

Key| Description  
---|---  
TotalCharges | (Integer) Total number of charges processed by the trebgp  
TotalEvents | (Integer) Total number of events processed by the trebgp  
TotalServices | (Integer) Total number of services considered for processing by the trebgp  
ExcludedServices  
| (Integer) The number of services that were eligible to be processed but were
excluded due them having no usage or rental charges associated with them.
This key can only contain a non-zero value if the EXCLUDE_IDLE_SERVICES
configuration attribute is set to TRUE.  
  
TotalCustomerNodes | (Integer) Total number of customer nodes processed by the trebgp  
MaxChargePasses | (Integer) Maximum number of passes to NE/CHARGE context by the trebgp  
MinChargePasses | (Integer) Minimum number of passes to NE/CHARGE context by the trebgp  
TariffChargesGenerated | (Integer) Total number of tariff charges generated by the trebgp  
SubtotalChargesGenerated | (Integer) Total number of subtotal charges generated by the trebgp  
Invoices | (Integer) Total number of inoices generated by the trebgp  
Statements | (Integer) Total number of statements generated by the trebgp. This includes invoice records for secondary accounts, invoice records for the primary accounts of non-reporting customer nodes (ie. those for which no statement   
image will be generated), and invoice records that have been converted to
statements pending consolidation.  
PendingConsolidation | (Integer) Total number of invoice records converted to statements pending consolidation by the trebgp. These statements are included in the total for the Statements statistics.  
InvoiceAmount | (Real) Total of invoice amounts generated by the trebgp  
StatementAmount |  (Real) Total of statement amount generated by the trebgp Only statements associated with customer nodes having a report level of Statement or Transferred, or invoices converted to statements pending consolidation, are included in this amount.  
RequestsSentToChildren | (Integer) Number of requests sent to children  
ResponsesReceived | (Integer) Number of responsed received from children  
ProcessingTime | (Real) Number of seconds spent processing requests.  This includes time spent waiting for responses ie. includes 'WaitTime'  
WaitTime | (Real) Number of seconds spent waiting for responses from children   
ProcessName | (String) The name of the BGP process, this will always be trebgp for the parent process  
ProductCombinationCache | (Hash) Statistics gathered from the BGP's internal ProductCombinationCache | SizeItems | (Integer) The number of items currently in the cache   
---|---  
SizeBytes | (Integer) The current size, in bytes, of the cache  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
MultiProductCombinationCache | (Hash) Statistics gathered from the BGP's internal MultiProductCombinationCache | SizeItems | (Integer) The number of items currently in the cache   
---|---  
SizeBytes | (Integer) The current size, in bytes, of the cache  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
DataTX| (Integer) The total size, in bytes, of all messages sent by this
process. This includes requests sent to children and responses sent to
children  
DataRX| (Integer) The total size, in bytes, of all messages received by this
process. This includes all requests and responses from children  
  
The hash contains the following statistics if the function is called from a
child process:

Key| Description  
---|---  
RequestsReceived | (Integer) Total number of requests received from the child's parent process  
RequestsSentToParent | (Integer) Total number of requests sent to parent process  
RequestsSentToChildren | (Integer) Total number of requests to sent to children processes  
ResponsesReceived | (Integer) Total number of responses received from children processes.  Does not include responses received from parent process.  
ProcessingTime | (Real) Number of seconds spent processing requests from parent.  This includes time spent waiting for responses ie. includes 'WaitTime'  
WaitTime | (Real) Number of seconds spent waiting for responses from children processes and from the parent process  
ParentProcessId | (Integer) The process id of the child's parent process  
MaxContext | (String) The maximum context of this child process  
ProcessName | (String) The name of the BGP process, this will always be bgp_child_process for the children processes  
ProductCombinationCache | (Hash) Statistics gathered from the BGP's internal ProductCombinationCache | SizeItems | (Integer) The number of items currently in the cache   
---|---  
SizeBytes | (Integer) The current size, in bytes, of the cache  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
MultiProductCombinationCache | (Hash) Statistics gathered from the BGP's internal MultiProductCombinationCache | SizeItems | (Integer) The number of items currently in the cache   
---|---  
SizeBytes | (Integer) The current size, in bytes, of the cache  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
DataTX| (Integer) The total size, in bytes, of all messages sent by this
process. This includes requests sent to the parent, requests sent to children
and responses sent to children  
DataRX| (Integer) The total size, in bytes, of all messages received by this
process. This includes requests from children processes, requests from the
parent process and responses from children  
  
#### Implementation

There are two types of statistics collected by the BGP: bill run statistics
and process statistics.  Bill run statistics are reset after each bill run
operation and are returned in the OperationStatistics?{} parameter in a
biInvoiceGenerate& call.  The BGP keeps a record of the cumulative bill run
statistics generated since boot time in a BillRunStats object. At the end of
every call to biInvoiceGenerate&, the statistics gathered during the bill run
operation are merged with these cumulative statistics. The BGP has a separate
BillRunStats object that contains the bill run statistics returned to the
parent process thus far for the current bill run.

Process statistics are collected for an individual process and are stored in a
BGPStats object.  These statistics are not reset after each bill run operation
and are not returned in the OperationStatistics?{} parameter to
biInvoiceGenerate&.

Calling BGPStats?{}() from the parent process returns the sum of the
cumulative bill run statistics, current bill run statistics and process
statistics.

If the function is called from a child process, the implementation is slightly
different. Each bgp child process keeps both bill run statistics and process
statistics.   Bill  run statistics are merged with the parent process's
statistics when the child has finished processing, then reset.  Process
statistcs are not merged up to the parent process and are not reset throughout
the life of the child process. Bill run statistics are stored in the
BillRunStats data member of the singleton class 'BGP'.   Process statistics
are stored in the singleton class BGPStats.

To retrieve the statistics for a child process, BGPStats::GetStats is called
to obtain a hash of statistics relevant to that process. This hash structure
is returned.

[EPM Functions] [Contents]

* * *

### Function InterimMode&

#### Declaration

InterimMode&()

#### Returns

TRUE (1) if the BGP is currently operating in interim mode.  FALSE (0)
otherwise.

#### Description

This function determines if the BGP is currently operating in interim mode.

#### Implementation

BGP_Config::GetInstance() is called to get a pointer to the singleton
BGP_Config instance. BGP_Config::IsInterimMode() is then called to determine
whether or not the BGP is currently operating in interim mode.

[EPM Functions] [Contents]

* * *

### Function BGP.BypassEventQueryMode&

#### Declaration

BGP.BypassEventQueryMode&(BillingConfiguration&)

**Parameters**

BillingConfiguration& | The configuration for the current bill run being processed the BGP. Corresponds to an Index 1 value in the BillingConfiguration derived attribute table.  
---|---  
  
#### Description

For the given billing configuration, determine whether the BGP should exclude
the NORMALISED_EVENT from the SQL query used to select charges.

#### Returns

TRUE if the NORMALISED_EVENT table is to be excluded and FALSE otherwise.

#### Implementation

This function is implemented in EPM code in the BASE_INSTALL group so that it
can be customised. The default implementation simply returns FALSE.

[EPM Functions] [Contents]

* * *

### Function BGPLogStatistics&

#### Declaration

BGPLogStatistics&()

#### Returns

TRUE (1) if the function executed correctly.  FALSE (0) if there was an error
while executing the function.

#### Description

This function is called periodically from within the BGP to log statistics to
the TRE Monitor. It first enables EPM and TRE statistics. It then compares the
hash returned from the current BGPStats?{}() call with the hash returned from
the previous call. If there are no differences the function returns and no
statistics are logged. Otherwise function biTREServerMonitor&() is called to
log the statistics gathered by BGPStats?{}() in the TRE Monitor.

#### Implementation

This function is implemented in EPM code. EPM and TRE statistics are enabled
by calls to stats_on() and treStatsOn&() respectively. Inter-call state
information (such as the result of BGPStats?{}() call) is maintained by global
variable ProcessState?{}.

[EPM Functions] [Contents]

* * *

### Function BGPTrace&

****

**Declaration**

    
    
    BGPTrace&(DebugLevel$)

****

**Parameters**  

  
DebugLevel$ | Diagnostic debug level.   
---|---  
  
**Returns**

Returns 1.

**Description**

This function sets the diagnostic debug level for this BGP to the level
specified by DebugLevel$. This value is interpreted in the same manner as the
configuration attribute.  

Setting a new trace level turns off any existing trace levels. Multiple
tracelevels can be set as shown in the following example:

`ecp ``biTrcBGP&('513') - Sets level 512 + level 1  
ecp biTrcBGP&('ORA,CUS') - Sets ORA(1) and CUS(512) `

Debug information requests are propagated to the BGP child processes via the
IPC pipes and each child takes the same action as the parent upon receiving
the message.  

**Implementation**

This function is implemented as a built-in function.  It is registered by the
BGP.

[EPM Functions] [Contents]

* * *

### Function biTrcBGP&

    
    
    **Declaration**
    
    
    biTrcBGP&(DebugLevel$)

**Parameters**

DebugLevel$ | The level of debug tracing required.  See the configuration item's debug level description for details on the levels.  
  
---|---  
  
**Description**

Sets the specified debug level for all the BGP servers running in the current
instance.  

**Implementation**

biTrcInvoke& is used to invoke the BGPTrace& function with the specified
DebugLevel$ within all BGP servers on the current instance.

[EPM Functions] [Contents]

* * *

### Function InvoiceAccountInserted&

#### Declaration

InvoiceAccountInserted&(const AccountId&)

#### Paramenters

AccountId& | The id of the account that was inserted against the current node.  
---|---  
  
#### Returns

Invoice Id created for the added account.  Aborts with an error on failure.

#### Description

This function notifies the BGP that an account has been inserted against the
node currently being processed. It may only be called from the NODE or lower
contexts.

The accounts for which invoices are required are determined early on by the
BGP during the first pass. It's necessary to notify the BGP if an account has
been added while processing so that it can update this list of accounts and
insert an invoice record.

[EPM Functions] [Contents]

* * *

### Function ServiceHasProduct&

**Declaration**

    
    
    ServiceHasProduct&(ProductName$)

**Parameters**

ProductName$ | The name of the product to search for  
---|---  
  
**Description**

Scans through the list of products for the service, comparing the name of each
with the name in ProductName$. The comparison **is case sensitive** , so
"Product_ABC" will not be found if the product's name is "Product_abc". If the
product named is not associated with this service, then this function will
return FALSE.

**Returns**

Returns TRUE if a product with the name ProductName$ exists on and is
associated with the current service, FALSE otherwise.  An error is raised if
this function is called from outside of the service context.

**Implementation**

Implemented as a built in function.  It is registered by the BGP and the ERT,
so the function is available in both the rating and billing environments. In
the BGP, the function queries the pass order to determine if the product is
present

[EPM Functions] [Contents]

* * *

### Function ServiceHasTariff&

**Declaration**

    
    
    ServiceHasTariff&(TariffName$)

**Parameters**

TariffName$ | The name of the tariff to search for  
---|---  
  
**Description**

Checks the service to determine if the tariff is present. Note if the tariff
has been overridden, it will not be found on the service. The comparison **is
case sensitive** , so "Tariff_ABC#" will not be found if the tariff's name is
"Tariff_abc#". If the tariff only belongs to products that are not associated
with this service, then this function will return FALSE. Global tariffs are
NOT considered to belong to a service.

**Returns**

TRUE if the current service has the tariff, FALSE otherwise.  An error is
raised if this function is called from outside of the service context.

**Implementation**

Determines if the tariff is present by querying the VarPassOrder, thus
overridden tariffs will not be detected. It is registered by the BGP and the
ERT, so the function is available in both the rating and billing environments

[EPM Functions] [Contents]

* * *

### Function ServiceProducts$[]

**Declaration**

    
    
    ServiceProducts$[]()

**Parameters**

None.

**Description**

Retrieves a list of product names associated with the service currently being
processed. This includes base product and companions. This function is only
available in the service context, any attempt to call it in another context
will result in an error being raised.

**Returns**

A string array containing a list of all product names associated with the
service currently being processed. The base product is always returned as the
first element in the array followed by associated companions. An error is
raised if this function is called from outside of the service context.

**Implementation**

Implemented as a built in function.  It is registered by the BGP and the ERT,
so the function is available in both the rating and billing environments. In
the BGP, the function queries the pass order to retrieve the list of product
names. Availability is restricted to the service context only.

[EPM Functions] [Contents]

* * *

### Function CustomerNodeHasProduct&

**Declaration**

    
    
    CustomerNodeHasProduct&(ProductName$)

**Parameters**

ProductName$ | The name of the product to search for  
---|---  
  
**Description**

Scans through the list of products for the customer node, comparing the name
of each with the name in ProductName$. The comparison **is case sensitive** ,
so "Product_ABC" will not be found if the product's name is "Product_abc".  If
the product named is not associated with any services belonging to this
customer node, then this function will return FALSE.

**Returns**

Returns TRUE if the customer node has a product matching the product name
passed in ProductName$, FALSE otherwise.  An error is raised if this is called
from a context other than the Customer Node context.

**Implementation**

Implemented as a built in function.  It is registered only by the BGP, so the
function is available only in the billing environment. The function queries
the pass order to determine if the product is present

[EPM Functions] [Contents]

* * *

### Function CustomerNodeHasTariff&

**Declaration**

    
    
    CustomerNodeHasTariff&(TariffName$)

**Parameters**

TariffName$ | The name of the tariff to search for  
---|---  
  
**Description**

Checks the customer node to determine if the tariff is present. Note if the
tariff has been overridden, it will **not** be found on the service. The
comparison **is case sensitive** , so "Tariff_ABC#" will not be found if the
tariff's name is "Tariff_abc#". If the tariff only belongs to products that
are not associated with services belonging to this customer node, then this
function will return FALSE. Global tariffs are NOT considered to belong to a
customer node.

**Returns**

TRUE if the current customer node has the tariff, FALSE otherwise.  An error
is raised if this function is called from outside of the customer node
context.

**Implementation**

Determines if the tariff is present by querying the VarPassOrder, thus
overridden tariffs will not be detected. It is registered by the BGP only, so
the function is available only in the billing environment

[EPM Functions] [Contents]

* * *

### Function CustomerHasProduct&

**Declaration**

    
    
    CustomerHasProduct&(ProductName$)

**Parameters**

ProductName$ | The name of the product to search for  
---|---  
  
**Description**

Scans through the list of products for the customer, comparing the name of
each with the name in ProductName$. The comparison **is case sensitive** , so
"Product_ABC" will not be found if the product's name is "Product_abc". If the
product named is not associated with any services belonging to this customer,
then this function will return FALSE.

**Returns**

Returns TRUE if the customer has a product matching the product name passed in
ProductName$, FALSE otherwise.  An error is raised if this is called from a
context other than the Customer context.

**Implementation**

Implemented as a built in function.  It is registered only by the BGP, so the
function is available only in the billing environment. The function queries
the pass order to determine if the product is present

[EPM Functions] [Contents]

* * *

### Function CustomerHasTariff&

**Declaration**

    
    
    CustomerHasTariff&(TariffName$)

**Parameters**

TariffName$ | The name of the tariff to search for  
---|---  
  
**Description**

Checks the customer to determine if the tariff is present. Note if the tariff
has been overridden, it will **not** be found on the service. The comparison
**is case sensitive** , so "Tariff_ABC#" will not be found if the tariff's
name is "Tariff_abc#".  If the tariff only belongs to products that are not
associated with services belonging to this customer, then this function will
return FALSE. Global tariffs are NOT considered to belong to a customer.

**Returns**

True if the current customer has the tariff, FALSE otherwise.  An error is
raised if this function is called from outside of the customer context.

**Implementation**

Determines if the tariff is present by querying the VarPassOrder, thus
overridden tariffs will not be detected. It is registered by the BGP only, so
the function is available only in the billing environment

[EPM Functions] [Contents]

* * *

### Function BillRunId&

**Declaration**

    
    
    BillRunId&()

**Parameters**

None |    
---|---  
  
**Description**

Returns the bill run id that the BGP is currently processing. This function
has an application environment of Billing and a context of Customer and is
thus accessible from any BGP context.

**Returns**

Returns the bill run id that the BGP is currently processing. This will always
be a positive number.

**Implementation**

Throws an exception if the bill run id has not been set.

[EPM Functions] [Contents]

* * *

### Function GetCurrencySymbol$

**Declaration**

    
    
    GetCurrencySymbol$(CurrencyId&, EffectiveDate~)

**Parameters**

CurrencyId& | Currency Id for whose symbol is returned.  
---|---  
EffectiveDate~ | The date at which the symbol is returned.  
  
**Description**

Returns the currency symbol which exists at the specified effective date for
the currency with the specified id.

**Returns**

Returns the currency symbol which exists at the specified effective date for
the currency with the specified id. Returns an empty string if a symbol does
not exist for the specified currency id / date combination.

**Implementation**

Uses the Currency Cache Module (ccm) GetSymbol(...) method to determine the
currency symbol.

[EPM Functions] [Contents]

* * *

### Function BilledCharge#

**Declaration**

BilledCharge#()

**Parameters**

None.

**Description**

Returns the sum of billable rated charges.

**Returns**

Sum of billable rated charges

**Note**

This function is only supplied for backward compatibility. All new
implementations should access the ChgInputBilledCharge# variable directly.

**Implementation**

Implemented as an EPM function.

[EPM Functions] [Contents]

* * *

### Function BilledProportion#

**Declaration**

BilledProportion#()

**Parameters**

None.

**Description**

Returns the proportion of the current billable rated charges

**Returns**

Proportion of the current billable rated charges

**Note**

This function is only supplied for backward compatibility. All new
implementations should access the ChgInputBilledProportion# variable directly.

**Implementation**

Implemented as an EPM function.

[EPM Functions] [Contents]

* * *

### Function TariffName$

**Declaration**

    
    
    TariffName$()

**Description**

Returns name of the tariff that generated the current charge.

**Returns**

The name of the tariff that generated the current charge. An empty string is
returned if the charge was not generated by a tariff.

**Implementation**

Implemented as an EPM function.

[EPM Functions] [Contents]

* * *

### Function TariffType&

**Declaration**

    
    
    TariffType&()

**Description**

Returns the tariff type code of the last billable rating tariff processed by
the biller.

**Returns**

The tariff type code of the last billable rating tariff processed by the
biller.

**Note**

This function is only supplied for backward compatibility. All new
implementations should access the ChgInputTariffType& variable directly.

**Implementation**

Implemented as an EPM function.

[EPM Functions] [Contents]

* * *

### SubtotalName$

**Declaration**

SubtotalName$()

**Parameters**

None.

**Description**

The SubtotalName function retrieves the name of the subtotal that generated
the current charge.

**Return Value**  
  
Name of the subtotal that generated the current charge, otherwise an empty
string if the charge was not generated by the subtotal.

**Implementation**

This function returns the value of the variable ChgInputSubtotalName$.All new
implementations should access the ChgInputSubtotalName$ variable directly.

[EPM Functions] [Contents]

* * *

### LoggerReload&

**Declaration**

LoggerReload&()

**Parameters**

None.

**Description**

This function is overridden in order to propagate the logger reload to child
processes. Otherwise, it provides the same functionality as  LoggerReload&(1).

**Return Value**  
  
1 on success. Raises an error otherwise.

[EPM Functions] [Contents]

* * *

## Initialisation

**Starting the BGP Server**

The BGP server can be invoked with the following command line options:

    
    
        trebgp -- <ConfigurationName|ConfigurationSeqNr>
    
    
    	eg trebgp -- BGP1
    

The arguments are as follows:

`**< ConfigurationName|ConfigurationSeqNr >**`

    This mandatory option specifies either Configuration Name or process number (Configuration Sequence Number) of the configuration item to use for this instance of the BGP. Multiple instances of BGP server may use the same process number.

### Server Boot Time

  * Read BGP configuration item.
  * Load all expression parser variables for the current date.
  * Determine variable evaluation order for the current date.

### Pre-processing Initialisation

  * Validate parameters from biInvoiceGenerate& or biInvoiceExplainPlan$ as appropriate.
  * Check that all expression parser variables for the effective date are loaded and in a stable state. If they are not loaded then load them.
  * Obtain locks on all root customer node ids.
  * Set the appropriate mode of operation.

### Loading Variables

The details of all expression parser variables effective on the effective date
of the bill run are retrieved from the database (iff they are not already
cached). This includes the following variables:

  * All direct variables with an application environment code of BILLING or less and a view name of CHARGE_INPUT_V, CHARGE_ASSIGN_V, NORMALISED_EVENT_V, SERVICE_HISTORY_V, CUSTOMER_NODE_HISTORY_V, CUSTOMER_V and INV_INVOICE_V.
  * All derived attributes with an application environment code of BILLING or less.
  * All tariffs with an application environment code of BILLING and RATING.
  * All subtotals.
  * All functions with an application environment code of BILLING, RATING or ANY.

### Variable Evaluation Order

Once all the variables have been read in, the order that the variables must be
evaluated is calculated.  A few assumptions are made to ensure the variables
are evaluated in an order which gives the shortest processing time possible.
These assumptions are described in more detail in the Variable Evaluation
Order SAS.

### Modes of Operation

The BGP Server is able to run in four distinct modes of operation depending on
which function is called and how it is called. These modes are:

  1. **Real Mode**  
If the biInvoiceGenerate& function is called with its QAInd& parameter set to
FALSE then the BGP will run in "real" mode. In this mode the BGP is generating
real invoices that will be sent out to customers.

  2. **Quality Assurance Mode**  
If the biInvoiceGenerate& function is called with its QAInd& parameter set to
TRUE then the BGP will run in quality assurance or "temporary" mode. In this
mode the BGP is generating temporary invoices that will be not be sent out to
customers and will not be paid. As the name suggests, this facility will be
used for quality assurance purposes and quoting. See Quality Assurance Bill
Runs for more information.

  3. If biExplainPlan$ is called then the BGP will produce an explanation of how a real bill run would be executed for the specified root customer node at the effective date provided. See biInvoiceExplainPlan$ for information on the type of information contained in the explanation. 
  4. **Interim Mode**  
If biInvoiceGenerate& is called with its InterimInd& parameter set to TRUE
then the BGP will run in "interim" mode.  This mode is intended for producing
invoices independent of a customer's regular invoice cycle. See Interim Bill
Runs for more information.

[Contents]

* * *

## Context Processing

After it's pre-process initialisation, the BGP starts processing the list of
root customer node ids, one at a time. This results in one or more calls to
BGP::ProcessCustomer(...) which processes the Customer context wrt the root
customer node id provided, this in turn, might start processing the Customer
Node context and so on, down to the Charge context.  An overview of general
context processing is shown below.

### Overview

  * Retrieve details from the higher context.
  * Retrieve entity details from the database.
  * Determine which variables are valid for this entity.
  * Calculate the number of hierarchy passes for this entity.
  * Determine which variables need to be passed to and from this entity during each hierarchy pass.
  * For each hierarchy pass:
    * Determine the child entities for this entity.
    * For each child entity:
      * Get variable values that need to be passed to the child entity.
      * Send details to the lower context.
      * Accumulate variable values received from the lower context.
    * Evaluate all variables for this context and hierarchy pass.
  * Send variable values to the higher context.

### Message from Higher Context

The higher (or parent) context sends a message to it's immediate lower context
with the following details:

  * Details of entity to process.
  * Values of higher context variables reference by the current or lower context.
  * Charges generated by tariffs or subtotals associated with other sections of the current customer hierarchy.

### Entity Details

The details of the entity specified by the parent context are retrieved from
the database and stored in direct variables in an expression parser associated
with the entity.  The context of the entity identifies the database table
containing the entity details and the direct variables used to store the
entity details.  The table below shows the names of the database tables and
direct variable views for each context.

Context | Table | View  
---|---|---  
Customer | CUSTOMER_V | CUSTOMER_V  
Aggregate Customer Node | CUSTOMER_NODE_HISTORY |    
Customer Node | CUSTOMER_NODE_HISTORY_V | CUSTOMER_NODE_HISTORY_V  
Service | SERVICE_HISTORY_V | SERVICE_HISTORY_V  
Normalised Event | NORMALISED_EVENT | NORMALISED_EVENT_V  
Charge | CHARGE | CHARGE_INPUT_V  
  
### Valid Variables

When the BGP processes an entity, only variables that are valid for that
particular entity are evaluated.  Variables matching the criteria listed below
are classed as valid variables.

  * All global tariffs and subtotals.
  * Non-global tariffs and subtotals associated with the current entity (by way of an associated product instance).
  * Direct variables, functions and derived attributes referenced by any valid subtotals and tariffs.

Note that the value of the ProcessState?{} global direct variable is
maintained per process when referenced at the NE and Charge contexts. A
separate copy is maintained for each of the Normalised Event and Charge
contexts.  
  
For the Service, Customer Node and Customer contexts, a separate copy is
maintained for each distinct entity at each context.

### Hierarchy Passes

The number of hierarchy passes performed during the processing of an entity
depends on the context and evaluation order of the valid variables for that
entity.

For example, if variables A, C, D and E are valid for Entity X (and the
context of each variable is as specified in the diagram below) then Entity X
will perform two hierarchy passes for the current context.  If variables A and
E are valid for Entity Y, then it will perform only one hierarchy pass for the
current context.

Figure ?. Calculating hierarchy passes

### Variable Values Passed Between Contexts

Once the set of valid variables for an entity has been determined, the
variables that need to be passed to other contexts are identified.  This
involves finding all valid variables that are referenced by another valid
variable at a different context.  The hierarchy pass that each variable is
passed in is also calculated.   In most cases, a variable value only needs to
passed to a context once and immediately before the first hierarchy pass that
references it as shown in the following diagram.  The cases where this is not
true are documented in the Variable Evaluation Order SAS.

Figure ?. Passing variables between contexts.

### Accumulating Variable Values From Lower Contexts

If a variable at a lower context is referenced by variable at a higher
context, the lower context evaluates the variable for each child entity and
passes the value up to the higher context entity where the values are
accumulated.  This accumulated value is then used when evaluating the higher
context variable.  The following diagram show an entity with three children.
Variable A at the current context references variable B at the lower context.
The value of variable A is the sum of variable B for each child entity.

Figure ?. Accumulating variable value from lower contexts.

Subtotal terms at a lower context than the subtotal itself are processed in
the same manner.

### Variable Evaluation

Valid variables of the current entity and hierarchy pass are evaluated once
the child entities have been processed.  Evaluating tariffs and subtotals may
generate charge records.

### Message to Higher Context

Once processing of the current context is complete, control is returned to the
higher (or parent) context along with a message containing details required by
the parent entity.   The following details are returned to parent entity:

  * Value of variables at the current or lower context referenced by variables at a higher context.
  * Value of subtotal terms at the current or lower context associated with subtotals at a higher context.
  * Charge values generated by tariffs or subtotals at the current or lower context retrieved from the database.
  * Tariff or subtotal values transferred to other entities within the current customer hierarchy.

### Customer Context Processing

Charge or variable values transferred to another customer node within the
current customer hierarchy are firstly transferred to the Customer context.
The Customer context then sends the values to the correct customer node the
next time it is processed.

### Customer Node Context Processing

The first time a customer node is processed, an invoice record is inserted
into the database.  This is done to ensure all charges generated for this
customer node reference a valid invoice record.  The last time a customer node
is processed, the invoice record is updated with the correct invoice or
statement amount. If the system has been configured to use receivable types
and if the node is an invoice node then the INVOICE_RECEIVABLE_TYPE table is
also populated on the last pass, immediately after the invoice is updated.

### Charge Context Processing

The Charge context retrieves and processes all charges associated with the
parent customer node and normalised event.  If the charge is associated with a
billable tariff (rating or billing) then the charge value is transferred to
the appropriate account of the customer node where it is added to the invoice
or statement amount. If the charge is non-billable but is associated with a
receivable type then it is transferred to the prime account of the appropriate
invoice node were it is aggregated according to the receivable type.

Return to contents.

* * *

## Quality Assurance Bill Runs

As the name suggests Quality Assurance or "temporary" bill runs are executed
to generate invoices for validation and quality assurance purposes. QA
invoices will not be sent to customers or applied to accounts. Typically a QA
bill run is executed for a subset of customers in the "real" bill cycle for
quality assurance before the "real" bill run on the scheduled bill run date.

When requested to process a Quality Assurance bill run, the BGP Server must
ensure that it does not interfere with other "real" bill runs. To achieve this
the BGP behaves differently with regard to charges that it reads and
generates, normalised events that it reads and invoice records that it
generates.

  * **Charges and Normalised Events  
**All charges that the BGP Server processes in a QA bill run are duplicated
and inserted into the CHARGE table as new QA charges with their
CUSTOMER_NODE_ID and INVOICE_ID fields set appropriately. This is in contrast
to the behaviour of a "real" bill run which _updates_ the existing CHARGE
records.  In a QA bill run the original CHARGE records are left unmodified in
the database ready to be processed in the next "real" bill run.   The BGP will
only process rental events (and their associated charges) generated in the
current bill run.  Rental charges are detected through the
NORMALISED_EVENT.BILL_RUN_ID being set to the bill run id that is passed into
biInvoiceGenerate&, only rental events have their NORMALISED_EVENT.BILL_RUN_ID
set.   This ensures that rental events from a past QA bill run will never be
invoiced on a "real" bill run even if the QA bill run wasn't completed.

  * **Invoices  
**When generating records in the INVOICE table for quality assurance bill runs
the BGP Server sets the QA_IND field to indicate that the invoice record is
temporary and may not accept any payments.

  * **Subtotals  
**The BGP sets the bill run id in the VDA accordingly to allow subtotal
functions to fetch the appropriate values.

  * **Inter-hierarchy transfer charges**  
Inter-hierarchy transfer charges are charges directed to an account in a
customer hierarchy other than the one that generated it. Inter-hierarchy
transfer charges generated during a QA bill run can cause problems for the BGP
because there is no guarantee that the customer the charge is directed to will
be processed in a QA bill run.  If the charge is processed in a "real" bill
run, then the invoice total generated in that bill run will incorrectly
include the QA charges, resulting in an inaccurate invoice total.

To overcome this the BGP provides two options:

    1. **Suppress inter-hierarchy transfer charges during QA bill runs**  
The default behaviour is to silently suppress inter-hierarchy transfer charges
during QA bill runs. If a charge is generated that is directed to an account
in a customer hierarchy other than the one that generated it, it is
suppressed. This creates the limitation that QA invoices will not include
inter-hierarchy transfer charges.

    2. **Filter out QA inter-hierarchy transfer charges during real bill runs**  
The second option is to generate inter-hierarchy transfer charges normally
during QA bill runs. However special verification is performed during both
real and QA bill runs to handle these charges correctly:

      1. _Real bill runs_ : during "real" (or non-QA) bill runs charges are filtered to exclude inter-hierarchy transfer charges generated during QA bill runs 
      2. _QA Bill Runs_ : during QA bill runs, inter-hierarchy transfer charges generated in a QA bill run are processed and associated with the current invoice (rather than the default behaviour of inserting a duplicate charge and associating the duplicate charge with the current invoice)
QA inter-hierarchy transfer charges are identified by having their
`FROM_INVOICE_ID` set to an invoice record that has its `QA_IND` field set to
TRUE. The BGP keeps a small `invoice_id->boolean` hashmap (cleared at the end
of each bill run) to keep track of which invoices correspond to QA bill runs.

This behaviour is enabled by setting ENABLE_QA_TRANSFER_CHARGES to TRUE. The
extra verification required when processing charges creates a minor
performance overhead (during QA and non-QA bill runs) when this mode is
enabled.

If this attribute is set to FALSE then inter-hierarchy transfer charges are
suppressed during QA bill runs (ie. option 1 above)

It's possible to exclude usage charges from a QA bill run by setting
EXCLUDE_QA_USAGE to true in the configuration item. In this mode usage charges
are excluded from processing and will not be invoiced. Other charges including
rentals, billing charges, payment and adjustments will appear on invoices as
per a normal QA bill run. This option can result in performance gains if it's
not a requirement that usage charges appear on QA invoices. The setting of
this attribute has no effect on standard bill runs.

Return to contents.

* * *

## Interim Bill Runs

If biInvoiceGenerate& is called with the InterimInd& parameter set to TRUE,
the BGP will be in interim mode for the duration of the bill run.

In an interim bill run, the BGP will only process events with their
bill_run_id set to the id of the current bill run. This limits the charges
that will appear on the invoice to those resulting from events created by the
RGP, charges generated by the BGP itself, and charges resulting from those
events that have had their bill_run_id explicitly set. Regular usage events
are excluded from the bill run.

Note that on an interim bill run the RGP will only create events for interim
tariffs so the invoice is generated completely independent to the customer's
regular billing cycle.    For example it would be confusing for a customer who
may be expecting a standard $20 per month rental amount and instead receives
$12.59 charge in the middle of the month and a $7.41 charge at the end.
Instead, if an interim bill run is performed in the middle of the month, the
standard $20 per month rental will not be affected; the interim bill run will
not contain a charge for this tariff.

Payments and adjustments are also ignored in an interim bill run. These will
be included on the next 'real' bill run.

[Contents]

* * *

## Selecting Charges for Invoicing

Generally speaking the BGP will invoice all uninvoiced charges that are
directed to an account belonging to the customer being processed, that have a
charge date less than or equal to the bill run effective date. This includes
charges generated by the customer itself and also charges generated by other
customers but transferred to the customer being processed.

However there are several aspects that can affect which charges are selected
for invoicing:

**Normalised Event Table SQL Join**

For normal processing of charges by the BGP, the SQL query to select charges
performs a join between the CHARGE table and the NORMALISED_EVENT table. Prior
to BGP processing, the NORMALISED_EVENT table is sorted (via sort_partition).
This results in an efficient SQL query for customers who own the service for
which the normalised event was generated.

However, in a revenue sharing scenario (for example) the customer being billed
may not be the customer owning the service. In this case, querying the
NORMALISED_EVENT table is inefficient, and if there are a large number of such
services performance may be poor. A performance improvement can be achieved by
configuring the BGP to exclude the NORMALISED_EVENT table from the SQL query.
To do this, the BGP.BypassEventQueryMode& function needs to be configured to
return TRUE for billing configurations that are used for solely for customers
that do not need NORMALISED_EVENT data to be processed the BGP.

This requires the BGP billing operation to have no expressions that use direct
variables populated from the NORMALISED_EVENT_V view.

The following table lists NORMALISED_EVENT_V columns that are duplicated in
the CHARGE_INPUT_V view and the corresponding direct variable populated from
that column.  Expressions and functions (such as GLGuidance?[]) should use
these direct variables instead of the corresponding NORMALISED_EVENT_V
variables.

BILL_RUN_ID | ChgInputBillRunId&  
---|---  
ROOT_CUSTOMER_NODE_ID | ChgInputRootCustomerNodeId&  
PERIOD_START_DATE | ChgInputPeriodStartDate~  
PERIOD_END_DATE | ChgInputPeriodEndDate~  
EVENT_CLASS_CODE | ChgInputEventClassCode&  
  
NOTE: The direct variables in the table above are populated regardless of the
return value of the BGP.BypassEventQueryMode& function.

#### Charge Partitions

If the CHARGE table is partitioned then the BGP queries the
ATLANTA_TABLE_PARTITION table to determine which charge partitions need to be
queried to retrieve charges for processing. This table is queried to retrieve
the start date of the oldest non-dropped charge partition that contains
uninvoiced charges where there is also an older, non-dropped partition that
_has_ been invoiced. Ie. there needs to be an invoiced charge partition,
followed by an uninvoiced charge partition.

Customers belong to customer partitions so this query is grouped by customer
partition number. Each customer partition will have minimum partition date.

The query that the BGP uses is given below:

    
    
    SELECT NVL(to_entity_id, 1),
           MIN(from_date)
      FROM atlanta_table_partition
     WHERE base_table_name = 'CHARGE' AND
           uninvoiced_ind_code = 1 AND
           actual_status_code != 3
     GROUP BY NVL(to_entity_id, 1)
     MINUS
    SELECT NVL(to_entity_id, 1),
           MIN(from_date)
      FROM atlanta_table_partition
     WHERE base_table_name = 'CHARGE' AND
           actual_status_code != 3
     GROUP BY NVL(to_entity_id, 1)
    
    

For each customer partition where no rows are returned, the date defaults to
"01-01-1994". This date is the start of the date range for which the BGP
retrieves charges for processing for customers belonging to that customer
partition. The end of the date range is determined by the
USAGE_BEFORE_BILL_DATE configuration attribute (see Usage Before Bill Date).

#### Usage Before Bill Date

The BGP can invoice usage charges _up to_ the effective date of the bill run
(ie. < bill run effective date); or up to _and including_ the bill run
effective date (ie. <= bill run effective date). The USAGE_BEFORE_BILL_DATE
configuration attribute gives control over this. This attribute is important
for end of month billing eg. a bill run is performed at midnight on the first
of the month but bills all usage charges for the previous month. In this case
USAGE_BEFORE_BILL_DATE should be set to TRUE. Note that this attribute only
affects usage events, rental events are not affected.

See the description of the USAGE_BEFORE_BILL_DATE configuration attribute for
more information.

#### Rental Charges

The BGP will only invoice rental charges generated in the current bill run.
Any rental charges generated in previous bill runs or transferred from
customers on different bill cycles will not be processed or invoiced.

Normalised events generated by the RGP have their bill_run_id populated with
the id of the bill run in which they were generated. Usage events do not have
a bill run id specified because they are generated independently of a bill
run. This bill_run_id field is queried when the BGP is retrieving normalised
events and charges for processing in the current bill run. Only events with
with no bill_run_id specified _or_ events with a bill_run_id equal to the
current bill run id are retrieved. Other normalised events (and their
associated charges) are not retrieved and are therefore not processed or
invoiced.

This means that if rental charges are not invoiced in the bill run in which
they were generated, they will _never_ be invoiced. If the charges need to
appear on an invoice they will need to be revoked and regenerated in a
subsequent bill run.

It also means that rental charges can only be transferred to customers on the
same invoice cycle.

#### Excluding Usage

In certain modes of operation the BGP will exclude usage charges altogether
and only process some or all of the other types of charges (rental, billing,
payments and adjustments)

Interim bill runs do not process usage charges or payments and adjustments.
Only rental charges are invoiced (see Rental Charges).

If EXCLUDE_QA_USAGE is enabled and the BGP is in quality assurance mode then
usage charges will not be processed.

#### Disputed Charges

The BGP ignores open account level disputed charges. It performs a query per
account on DISPUTE and DISPUTE_CHARGE to determine which disputes are open
account level disputes. It stores the list of disputed CHARGE_IDs per account
and uses this list to exclude these charges during charge processing.

[Contents]

* * *

## Invoice Generation

On the BGP's first pass, if it is running in "real" (QAInd& set to FALSE)
mode, all charges to be processed are modified to include the id of the
invoice that is associated with the customer node being processed. However, if
running in "quality assurance" mode, the BGP will insert new QA charges (with
the invoice id set) for all non-recurring charges that would normally be
processed in "real" mode. These QA charges for the remainder of the bill run.
Recurring charges are modified regardless of the value of the QAInd parameter.
All subsequent passes will query the charge and event tables based on the
invoice id.

This allows quality assurance bill runs to be processed transparently and also
prevents any usage charges that come in between the first BGP pass and it's
last pass from being erroneously included in the current bill run. When a new
invoice record is created the RUNNING_IND_CODE is set to indicate that the
invoice is being processed. Once all customer nodes have been processed, the
customer hierarchy tree is traversed one last time to update the invoice
records for each account associated with the customer nodes and reset the
RUNNING_IND_CODE column.

The BGP uses default expressions to calculate values for some of the invoice
direct variables associated with the INV_INVOICE_V database view. All values
from the INVOICE table on the view can be overwritten by the user-defined
invoice type expressions. However, changes to the InvInvoiceId& and
InvInvoiceEffectiveDate~ direct variables are not supported. Changes to the
InvInvoiceAmount# or InvStatementAmount# direct variables are also not
supported for receivable type accounts. Any such changes will be ignored by
the BGP. Invoice values are not re-calculated after evaluating invoice type
expressions if their dependent values are modified.

The BGP suppresses invoices when the value of SUPPRESS_IND_CODE column is 1.
The value of this flag can be set by the direct variable InvSuppress& in the
invoice type expression. If all invoices in a customer hierarchy have this
flag set for a bill run, then the invoices and statements will be immediately
revoked including any rental charges and adjustments run for this customer
hierarchy and bill run. If only some of the invoices in a customer hierarchy
have this flag set for a bill run, then it has no effect. However, the flag
will remain set for those invoices in the hierarchy that qualified for
suppression.

The default expression used by the BGP are shown below.

Direct Variable | Value | Updatable | Notes  
---|---|---|---  
InvInvoiceId& | Invoice Identifier | No |    
InvInvoiceAmount# | Invoice amount as calculated by the BGP | Yes (Not updatable for receivable type accounts) | Either the invoice amount or statement is populated but not both  
InvStatementAmount# | Statement amount as calculated by the BGP | Yes (Not updatable for receivable type accounts) | Either the invoice amount or statement is populated but not both  
InvInvoiceEffectiveDate~ | Effective date of the bill run | No |    
InvIssueDate~ | InvInvoiceEffectiveDate~ | Yes | The invoice is applied to the account as of the invoice issue date, and unexpected behaviour can result if it is not set correctly. If the issue date is set to a date after the effective date of the next scheduled bill run, the balance forward amount of that invoice will not reflect the current invoice amount (as the balance forward is retrieved as of the bill run effective date).  Similarly if the issue date is set to a date in the past, the balance forward of prior invoices will not reflect the current invoice amount. It is recommended that InvIssueDate~ be set to a date 

  * >= InvInvoiceEffectiveDate~ of the current bill run; and 
  * < InvInvoiceEffectiveDate~ of the next scheduled bill run

  
InvOriginalPaymentDueDate~ | InvIssueDate~ | Yes |    
InvPaymentDueDate~ | InvIssueDate~ | Yes |    
InvCustomerInvoiceStr$ | to_string(InvInvoiceId&, '#') | Yes |    
InvAccountBalance# | If the invoice is associated with a liability account and the v8.00 accounting functionality is enabled :-InvBalanceForward# - DeltaAmount otherwise :- InvBalanceForward# + DeltaAmountwhere :-DeltaAmount is equal to InvInvoiceAmount# for invoicing accounts and InvStatementAmount# for statement accounts | Yes |    
InvAccountInitialDue# | InvAccountBalance# | Yes |    
InvCurrentDue# | InvInvoiceAmount# | Yes |    
InvSuppress& | Undefined / Null | Yes (Not updatable if previous statement is still pending consolidation) | Set to 1 to suppress the invoice. All invoices and pending consolidation statements in a hierarchy must be suppressed for suppression to take effect  
InvPendingConsolidation& | Undefined / Nullor 1 if the previous statement for this account is still pending consolidation (in this case the variable is not updatable) | Yes (Not updatable if previous statement is still pending consolidation) | Set to 1 to convert the invoice to a statement pending consolidation. See Pending Consolidation below  
  
Variables referenced in invoice type expressions, including dependencies of
those variables, are taken into consideration when building the variable
evaluation order for the customer node with which the invoice is associated.
Therefore it is guaranteed that any variables referenced in invoice type
expressions will be pre-evaluated and able to be referenced from the
expressions. Note however that it is impossible to evaluate a tariff or
subtotal that is not associated with a product associated with the customer
node as information is needed from the product definition such as charge
category details and invoice text. Therefore any tariffs or subtotals
referenced _only_ in an invoice type expression (that is, are not _also_
associated with a product definition) are silently ignored.

Statement amounts for _non-invoicing_ nodes are transferred up the customer
hierarchy tree and added to the invoice amount of the next highest _invoicing_
node.  To calculate invoice amounts correctly, customer nodes are processed in
reverse hierarchy order (ie. all child nodes are processed before their parent
node). Non-invoicing nodes having an existing non-zero account balance do not
affect the outcome of a bill run. Manual payments/adjustments must be used to
reduce any outstanding amounts (debit/credit) on non-invoicing nodes.

Invoices are not generated for accounts that are closed (the account history
is end dated) as of the bill run effective date. An error is reported if a
charge is processed or generated for an intra-hierarchy account that is
closed.

If the system is using receivable types then immediately after the node's
invoice record is written to the INVOICE table, the INVOICE_RECEIVABLE_TYPE
table is populated with the node's invoice / receivable type break down. A
record is written to the INVOICE_RECEIVABLE_TYPE table for each aggregated
receivable type detailing the total amount of charges that have been
aggregated against that receivable type. An additional record is written
against the default receivable type if there is a discrepancy between the
total amount aggregated against receivable types and the total invoiced
amount. This additional record ensures that the total amount allocated to
receivable types is the same as the total invoices amount for the account.
For each record inserted into the INVOICE_RECEIVABLE_TYPE table a
corresponding record is written to the INVOICE_HISTORY table

If the system is not using receivable types and the invoice amount is not zero
a record is written to the INVOICE_HISTORY table with a null receivable type.

#### Pending Consolidation

In some cases it is necessary to prevent an invoice point from receiving and
being responsible for paying an invoice. For example if an invoice point does
not reach a threshold amount of usage over the month then the billing of that
invoice point may be suppressed until a subsequent bill run. In this case,
instead of inserting an invoice record, a statement is inserted that is
pending consolidation. This statement will be consolidated (potentially with
other statements) into an invoice at a later point in time.

Invoice consolidation generally occurs on a per account basis, in which case a
series of invoices for an account are suppressed until the statements are
consolidated and invoiced. For example an invoice point may not reach a
threshold number of calls for January and February however in March the
statements for the period January to March are consolidated into an invoice
for which that the customer is responsible for paying.

Statements can also be consolidated from multiple accounts in multiple
hierarchies. In this case root customer nodes are configured prior to the bill
run with a reporting level of _Transferred Statement_ and the external account
to which the statement amount is to be transferred. The BGP will automatically
insert statements pending consolidation for these customers.

An invoice is switched to a statement pending consolidation in the following
cases

  1. An invoice type expression sets the `InvPendingConsolidation&` direct variable to 1. This direct variable corresponds to the `PENDING_CONSOLIDATION_IND_CODE` column in the INVOICE table
  2. The customer node being processing has a reporting level of _Transferred Statement_. In this case the statement will be consolidated when the customer that `TRANSFERRED_ACCOUNT_ID` is associated with is processed.

If an invoice is switched to a statement pending consolidation the following
changes are made to columns for the INVOICE record:

PENDING_CONSOLIDATION_IND_CODE | 1  
---|---  
STATEMENT_AMOUNT | Invoice amount as calculated by the BGP  
INVOICE_AMOUNT | 0.0  
INVOICED_ACCOUNT_ID | NULL  
  
The statement amount is not rolled up to a parent invoice point.

If any previous statements for the account are still pending consolidation,
then the current invoice is automatically switched to a statement pending
consolidation and also cannot be suppressed. This behaviour cannot be
overridden by the invoice type expressions.

Similarly if there is a statement pending consolidation in the database
associated with an account with a `TRANSFERRED_ACCOUNT_ID` of the account
being processed then the current invoice is automatically switched to a
statement pending consolidation.

Return to contents.

* * *

## Variable Purging and Reloading

Because the BGP is implemented as a tuxedo server and therefore may be running
for an extended period of time, and because bill runs may be requested at
virtually any effective date, the BGP must be aware of and able to resolve any
changes to variables and products that will have an impact on the value of a
customers invoice.

The BGP Server will keep a cache of date ranged variable pass order objects
that are able to be retrieved for a specified date. When the state of a
variable or product is changed through the Client, the BGP Server receives a
notification to purge and reload the affected variable. If any of the
variables dependencies change, the evaluation order and pass order will be
updated to reflect the new dependencies. Likewise, if the date range of a
variable changes the evaluation order and pass order will be updated to
reflect the new start and end date of the variable, this may result in caches
being split or merged. If the date of a bill run has not been previously
encountered by the server a new variable evaluation and pass order is created
and cached before the run commences.

For more information on variable purging and reloading, see the Variable
Evaluation Ordering (VEO) SAS.

Return to contents.

* * *

## Variable Evaluation

### Subtotal Evaluation

If a subtotal term is eligible, it is evaluated.  If it is in the same context
as the subtotal, or it is associated with a running subtotal, its value is
added to the corresponding subtotal variable in the current context entity's
parser.  If the subtotal variable is at a higher context, then the subtotal
term value is transferred to that context and added to the subtotal variable
in the entity's expression parser.  A subtotal with aggregation type of Min or
Max is considered ineligible if its aggregated value is undefined as a result
of all its terms being ineligible.  When the subtotal is evaluated, it is
checked for eligibility, and if eligible and it is not a temporary subtotal, a
charge is inserted into the CHARGE table containing the accumulated subtotal
term values.   If the subtotal is not eligible then the subtotal variable is
undefined.   Since the BGP processes subtotal terms before the actual
subtotal, it may evaluate a eligible term unnecessarily if the subtotal is not
eligible.

For keyed subtotals, a CHARGE record is written for each key value that the
subtotal contains. This charge record will contain the subtotal value that
corresponds to this key value in the CHARGE field of the CHARGE table. Keyed
subtotals may also generate a unique receivable type for each key value. If
this is the case then the value of the subtotal that corresponds to the key
value which generated the receivable type is aggregated into the receivable
type. For more information on receivable types see Split Receivables.

**Future Enhancement:** Determine subtotal eligibility before evaluating the
terms.

The CHARGE record produced by the subtotal has an ACCOUNT_ID of the prime
account of the customer. The ACCOUNT_ID can be overridden for service context
subtotals through the BillingServiceAccountId&() function. This service
context function has access to the service context variables and can return
the account id of the secondary account to direct the charge to. The account
id returned must be an account of the customer node that owns the service. If
an account id is specified, the INVOICE_ID of the inserted charge corresponds
with the specified secondary account id. The default NULL return value
indicates that the BGP should use the existing behaviour of associating the
subtotal charge with the primary account.

A billing subtotal at a particular context will only be evaluated once for
each entity belonging to that context. For example, a Service context billing
subtotal associated with a particular customer node that has one service
instance and two accounts (a prime account and a secondary account) would
produce a single CHARGE record that is associated with the prime account, or
the secondary account if returned from the 'BillingServiceAccountId&()'
function. It would accumulate all eligible charges underneath the customer
node, regardless of what account they have been directed to. In order to only
have a subtotal accumulate charges associated with a specific account, the
subtotal term eligibility would have to be used to only include charges
directed to the desired account.

#### Subtotal Terms

A subtotal may have one or more terms. Terms must be at a context less than or
equal to the subtotal itself.  Each term can almost be thought of as a
separate variable that needs to be evaluated at a different context to the
subtotal itself. As terms are evaluated they are automatically passed up to
the context of the subtotal where they are aggregated to the value of the
subtotal.

It's important to note that subtotal _terms_ will only be evaluated for
entities that are aware of the _subtotal_ by having it explicitly associated
with a product associated with that entity. Eg. A subtotal at the Customer
context has a term at the Node context.  The subtotal term will only be
evaluated for customer nodes that have that subtotal associated with them (via
a product definition). Any nodes that have no products sold to them or have
products that don't include the subtotal will not contribute to the subtotal.

A subtotal with the _include amounts from child nodes_ checkbox enabled
accumulates values from all the child nodes as well as the current node.  A
subtotal of this type must have a context of Customer Node.  If the subtotal
has a _Not Aggregate Expression_ specified, the value is not passed up to the
parent node if the expression evaluates to true (ie. a non-zero value).

A subtotal with the _examine normalised events for all accounts_ checkbox
enabled aggregates all its terms for the same service under all accounts in
the current customer hierarchy.  The subtotal value is only stored in the
service expression parser associated with the customer node that owns the
service.  For all other instances of the service in the hierarchy, a value of
zero is assigned to the subtotal variable with the associated charge record
containing the aggregated subtotal value.

A subtotal with the _store result for use in future bill runs_ checkbox
enabled stores its value in the SUBTOTAL_VALUE table as well as the CHARGE
table. If a persistent subtotal is keyed then a record is stored in the
SUBTOTAL_VALUE table for each key value contained in the subtotal. The
subtotal amount that corresponds to this key value is also stored in the
SUBTOTAL_VALUE table.

A subtotal with the _use subtotal before final value_ checkbox enabled is used
to store a progressive value that can be accessed by other variables before
the final subtotal value is calculated.  A subtotal of this type is not
included when determining the number of passes through the customer hierarchy.
This means that the subtotal can be accessed by a lower context variable
without causing a new pass through the hierarchy.

A subtotal with the _suppress zero_ checkbox enabled does not insert a record
into the CHARGE table when the subtotal value is zero.

A subtotal with the _Temporary Subtotal_ check box ticked is never written to
the CHARGE table.

A subtotal with the _Global_ check box ticked implies that the subtotal is not
associated with any product. Only global subtotals can be used to total
payments and adjustments made against a customer's account. This is because
all payments and adjustments are processed under the null service which is
like a dummy service with no products.

### Tariff Evaluation

Evaluating an eligible tariff generates one or more charges depending on the
charge category associated with the tariff.  A record is inserted into the
CHARGE table for each charge generated by the tariff.  If the charge is for an
account associated with the current entity, then the charge value is added to
the tariff variable in the entity's expression parser.

For keyed tariffs, a CHARGE record is written for each key value that the
tariff contains. This charge record will contain the tariff value that
corresponds to this key value in the CHARGE field of the CHARGE table. Keyed
tariffs may also generate a unique receivable type for each key value. If this
is the case then the value of the tariff that corresponds to the key value
which generated the receivable type is aggregated into the receivable type.
For more information on receivable types see Receivable Types .

A tariff with the _suppress zero_ checkbox enabled does not insert a record
into the CHARGE table when the tariff value is zero.

### Sending Charges to Other Accounts

It is possible for a billable tariff to send all or part of it's value to
another account.   This _other_ account can be within the current customer
hierarchy (intra-hierarchy tariff) or in another hierarchy entirely (inter-
hierarchy tariff).  If the _other_ account is in the current hierarchy then
the BGP returns to the Customer context (ie. inserts a new Customer hierarchy
pass) before the next variable that references this tariff is processed.  This
is done so that the tariff value can be transferred to the correct part of the
hierarchy before the next variable to reference this tariff is evaluated.  A
new pass is not inserted if one already exists.

When a intra-hierarchy tariff transfers its charge (or a proportion of its
charge) to its _to_ or _from_ account the value is added to the tariff
variable in the expression parser associated with the account.  If the tariff
is a Customer context tariff then its value is added to the tariff variable in
the Customer entity expression parser. If the tariff is a Customer Node
context tariff then its value is added to the Customer Node entity expression
parser associated with the account.  If the tariff is a Charge, Normalised
Event or Service context tariff then a copy of the service that the tariff was
evaluated in is added to the _other_ customer node and the tariff value is
added to the tariff variable in the expression parser of this new service.
This phantom service is then processed just like the original service.

If a transfer tariff has a different _from_ and _to_ account that are
associated with the same customer node then only the _to_ account charge is
added to the tariff variable.

Intra-hierarchy transfer charges generated prior to billing have a charge
record in the database at the time the BGP is generating the variable pass
order for the hierarchy.  Because of this the _destination_ entity (either
customer node or service) is aware of any variables referenced in the product
the transfer charge is associated with and these variables are included in the
variable pass order. When a billing intra-hierarchy transfer charge is
generated, however, the variable pass order of the destination entity needs to
be _dynamically_ modified to accommodate the new product definition.

To handle this situation, the BGP will check if any new products have been
processed at a lower context (via transfer charges) when processing a message
from a lower context. If a new product is detected the variable pass order for
the product is merged with the variable pass order of the current entity.
Merging the variable pass orders is not always possible however; variable pass
orders are considered incompatible if one of the following conditions is true
:-

  1. A variable in the product variable pass order with a context equal to or higher than the context of the current entity does not exist in the current entity's variable pass order
  2. A variable in the product variable pass order is passed down from a higher context and there is no equivalent pass variable in the current entity's variable pass order

If the variable pass orders are incompatible the BGP will fail with an error
message similar to the following :-

<E03127> bgp: The dynamic addition of product "Transfer Product" to service
"MyService" has resulted in an unexpected variable

It is possible to modify configuration to recover from this error. The error
is stating that while dynamically adding the variable pass order it is
encountering some variables that it doesn't know about. The solution is to
make the destination entity aware of the variables. This can be done by adding
the product ("Transfer Product" in the case above) to the destination service
or by adding references to any variables referenced in "Transfer Product" to a
product associated with the destination service. Eligibility expressions may
need to be modified to ensure correct functionality.

Return to contents.

* * *

## Tariffs

When a billing tariff is evaluated by the BGP, it can generated one or more
charges which can be sent to a number of different accounts.  The number of
charges generated by a tariff depends on the details of the charge category
used by the tariff.

### Charge Categories

A global tariff uses the details of the charge category specified when the
tariff was created (TARIFF_HISTORY table).  A non-global tariff uses the
charge category details associated with the current service (for Charge,
Normalised Event and Service context tariffs, ie. SERVICE_CHARGE_CATEGORY
table) or the current customer node (for Customer Node and Customer context
tariffs, ie. CUSTOMER_NODE_CHARGE_CAT table).

### Accounts

The _from_ and _to_ account id of the charge category is used unless the
tariff has a _from_ or _to_ account expression specified.  Account expressions
are evaluated when the tariff is evaluated.  If an account expression
evaluates to a zero value then the account id specified in the charge category
is used.   If an account expression evaluates to a negative value then the
account id is not specified (this applies to the _from_ account expression
only as a _to_ account must always be specified).  If an account expression
evaluates to a positive value then that value is used as the account id.   No
validation is performed to verify that the result of an account expression is
a valid account id.  An invalid account id will cause the BGP to terminated
with an error.

### GL Codes

The _from_ and _to_ gl code id of the charge category is used unless the
tariff has a _from_ or _to_ gl code expression specified.  GL code expressions
are evaluated when the tariff is evaluated.  If a gl code expression evaluates
to a zero value then the gl code id specified in the charge category is used.
If a gl code expression evaluates to a negative value then the gl code id is
not specified (this applies to the _from_ gl code expression only).  If a gl
code expression evaluates to a positive value then that value is used as the
gl code id.   No validation is performed to verify that the result of a gl
code expression is a valid gl code id.    An invalid gl code id will cause the
BGP to terminated with an error.

If a tariff has a _from_ gl code id but no _from_ account id then the _from_
gl code id is assigned to the FROM_GL_CODE_ID column of the charge record
generated for the _to_ account.

### Account Class Codes

If v8.00 accounting functionality is enabled, all charges sent to a _from_
account are negated, irrespective of account class. If v8.00 accounting
functionality is disabled,  the charge is only negated if the _from_ account
class code is equal to the _to_ account class code or is not specified. For
inter-hierarchy _to_ or _from_ account ids not specified by the charge
category, the account classes may be determined from the Account cache if
available, otherwise they are fetched using biAccountFetchRealTime&().

### Invoice Text

A tariff's invoice text can be specified in three different places during
configuration.  The rules that govern which invoice text is used when
generating the tariff charge records are described below.

  1. If a row in the tariff's definition table is used to calculate the value of the tariff then the invoice text associated with that row, if any,  is used (TARIFF_CHARGE table); or
  2. If the tariff is non-global then the invoice text associated with the current product is used (PRODUCT_TARIFF table).  If there is more than one product with an invoice text for this tariff (which can occur for Customer or Customer Node context tariffs) then the BGP will use the first valid invoice text in finds.
  3. If the tariff is global then the invoice text specified during tariff creation is used (TARIFF_HISTORY table).

### Prioritisation

When a tariff is placed on a product it may be assigned a priority. These
priorities determine which tariffs will be evaluated for a service, where the
service has multiple products.

  * See the Tariff Priority Module (TPM) for more information on how the priority systems works. 
  * See the Variable Evaluation Ordering (VEO) SAS to see how tariff prioritisation affects variable ordering. 
  * See the Detailed Design Document to see how the prioritisation has been implemented in the BGP.

Return to contents.

* * *

## Special Direct Variables

Billing variables have access to special direct variables not associated with
a database view.  These variables allow access to information calculated
internally by the BGP.   At this stage, only internal information on the
current charge being processed can be accessed using these variables.  The
following table lists the name, context and description of each special direct
variable.

Name | Context | Description  
---|---|---  
ChgInputBilledCharge# | Charge | Charge value if charge generated by a billable rating tariff.  
ChgInputBillable& | Charge | 1 (TRUE) if charge generated by a billable tariff.  
ChgInputBilledProportion# | Charge | Charge proportion if charge generated by a billable rating tariff.  
ChgInputTariffType& | Charge | Type of tariff that generated the charge.  
ChgInputApplicationEnv& | Charge | Application environment code of the tariff or subtotal that generated the charge.  
ChgInputTariffName$ | Charge | Name of the tariff that generated the charge.  
ChgInputSubtotalName$ | Charge | Name of the subtotal that generated the charge.  
ChgInputAccountCurrencyId& | Charge | Currency of the account associated with the current charge  
ChgInputAccountClass& | Charge | Account class code of the account type of the charge's account  
ChgInputAccountCategory& | Charge | Account category code of the account type of the charge's account  
  
Return to contents.

* * *

## Associated Companion Products

Companion products that belong to a service are not always considered
"associated" to that service, for billing purposes.

For instance, when a companion product is cancelled, it still "belongs" to the
service, but none of its tariff should now be used for billing. In effect it
is no longer associated to the service.

Determining whether or not a companion product, is associated with a service
is not straight-forward.  The following three rules are used in determining
association:

**Rule 1.** An active companion product is always associated with a service
regardless of the services status.

**Rule 2**. A companion product instance is considered to be associated with a
service if it has the same status as the service and is not cancelled.

**Rule 3**. If both service and companion product have a status of cancelled,
they must both have been cancelled at the same time. If they were not
cancelled at the same time, the companion product is not considered
associated.

**Explanation**

Rule 1 allows tariffs and subtotals associated with a companion to be applied
to the service if the service's status does not match the companion.

Rule 2 allows for the provisioning of a companion product, before it becomes
active.   The service must be active in order to be billed, therefore, if the
companion product's status differs from the service's, then it can not be
associated, (active for billing).

Events may still arrive for billing for a service that has been cancelled.
These events still need to be billed. Rule 3 caters for this.  It effectively
says, if the companion was active right up until the time the service was
cancelled, then for the received event, consider the companion associated (ie
active for billing).  If the companion was cancelled prior to the service
being cancelled, then assume the companion's cancellation was intended to be
effective for the received event.

[Contents]

* * *

## Multiple Processes

### Server Processes

Depending on the configuration item details the BGP Server may run with
multiple spawned processes or as a single process. If the
NODE_CHILD_PROCESSES,  SERVICE_CHILD_PROCESSES, EVENT_PROCESSES and
CUSTOMER_CHILD_PROCESSES attributes all contain a value of zero (default) or 1
then all bgp processing is done within the server process. However, if one of
these attributes contains a value greater than 1 then the BGP Server will
spawn (fork/exec) a parent BGP process which in turn will fork the specified
number of child processes. When running in multi process mode, the BGP Server
will only manage the customer node lists, all bgp processing will be done in
the spawned bgp parent process. In this case the server will act as a proxy to
the bgp parent process. See the bgp_ddd for more information.

The following diagram illustrates this:

If the multi-process option is enabled, the BGP Server first forks and
executes a BGP parent process which in turn forks a number of child processes
that process sections of a bill run in parallel.  The BGP parent process can
fork three types of child processes, Customer Node, Service and Sub Service.
As the names suggest, a Customer Node child process processes customer nodes
and a Service child process processes services. Sub Service processes allow
the processing of services to be broken up over a specified number of forked
processes. Event level concurrency is designed to allow the BGP to scale when
processing high volume services such as those associated with call centres.
Unless the bill run contains these type of service there is no value in this
level of multi-processing.

The number of child processes that the BGP forks is specified by configuration
attributes NODE_CHILD_PROCESSES, SERVICE_CHILD_PROCESSES,
EVENT_CHILD_PROCESSES and CUSTOMER_CHILD_PROCESSES in the BGP configuration
item. The BGP can be configured to use any combination of process types at the
same time by specifying the above attribute types as a positive integer. Even
though the BGP will allow service and customer node process to be run at the
same time, it is considered that this will not give any performance
enhancement.

If multi-tenancy is in use, the effective tenant is not propagated to child
processes and therefore child processes will not run with an effective tenant.
For this reason, if multi-tenancy is enabled, the BGP should be configured not
to use child processes, as the child processes will not be able to correctly
retrieve tenanted configuration.

The table below shows the maximum number of child processes forked for each
configuration (assuming all event level children are forked during a bill
run). It can be seen from this table that the total number of spawned
processes will grow exponentially as lower context processes are forked. Note
that event level children are only spawned if they are required during the
bill run. This can dramatically reduce the total number of forked processes,
and consequently memory, if there are fewer services that require event level
processing than the number of processes configured to process the service
context. Care needs to be taken when configuring the BGP to restrict the total
number of spawned processes to a realistic number that is compatible with the
number of cpu's available.

Attribute Type value | Number of Parent BGP processes. | Number of Customer Node child processes | Number of Service child processes | Number of Event child processes | Total number of spawned processes  
---|---|---|---|---|---  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES 0  
EVENT_CHILD_PROCESSES 0 or 1 | None | None | None | None | None  
CUSTOMER_CHILD_PROCESSES _c_  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES 0  
EVENT_CHILD_PROCESSES 0 or 1 | _c_ | None | None | None | _c_  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES _n_  
SERVICE_CHILD_PROCESSES 0  
EVENT_CHILD_PROCESSES 0 or 1 | 1 | _n_ | None | None | _n_ +1  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES 0 or 1 | 1 | None | _s_ | None | _s_ +1  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES 0 _  
_ EVENT_CHILD_PROCESSES _ss_(>1) | 1 | None | None | _ss_ | _ss_ +1  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES _n_  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES 0 or 1 | 1 | _n_ | _n_ *_s_ |   | 1+_n_ +(_n_ *_s_)  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES _ss_(>1) | 1 | None | _s_ | _s*ss_ | 1+_s_ +(_s*ss_)  
CUSTOMER_CHILD_PROCESSES _c_  
NODE_CHILD_PROCESSES _n_  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES 0 or 1 | _c_ | _c*n_ | c*n*s | None | _c_ +(_c*n_)+(_c*n*s_)  
CUSTOMER_CHILD_PROCESSES _c_  
NODE_CHILD_PROCESSES 0  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES _ss_ | _c_ | None | _c*s_ | _c*s*ss_ | _c_ +(_c*s_)+(_c*s*ss_)  
CUSTOMER_CHILD_PROCESSES 0  
NODE_CHILD_PROCESSES _n_  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES _ss_ | 1 | _n_ | _n_ *_s_ | _n*s*ss_ | 1+_n_ +(_n_ *_s_)+(_n_ *_s_ *_ss_)  
CUSTOMER_CHILD_PROCESSES _c_  
NODE_CHILD_PROCESSES _n_  
SERVICE_CHILD_PROCESSES _s  
_EVENT_CHILD_PROCESSES _ss_ | _c_ | _c*n_ | _c*n_ *_s_ | _c*n*s*ss_ | _c_ +(_c*n_)+(_c*n_ *_s_)+(_c*n_ *_s_ *_ss_)  
  
### Inter-Process Communications

All process to process communications is performed by sending messages through
unnamed Unix pipes.  When a process is forked or execed (parent process), two
unnamed pipes are created, one for the parent to send messages to the child,
and the other for the child to send messages back to the parent.  The BGP
creates twice as many unnamed pipes as there are spawned processes.  Once a
child process is forked, it blocks until a message is received from the parent
process.  It processes the message then returns a completion message back to
the parent.

The parent process sends as many pending messages as possible to the available
child processes.  It then blocks waiting for a child to finish processing and
return a completion message.  Once the parent receives a message it either
sends another pending message back to the child (which is now available) or if
no more pending messages exist, blocks until all children have finished.

### BGP Parent (Customer) Process

The parent process processes a single customer at a time. If the BGP is
configured to spawn Customer Node child processes, the nodes in the hierarchy
are processed in CUSTOMER_NODE_HISTORY.BILLING_PRIORITY order. Once a customer
has finished being processed it notifies the server by returning a completion
message.  The server then sends a message back to the bgp parent informing it
to start processing the next customer.

### Customer Node Child Process

A Customer Node child process processes one or more customer nodes associated
with a customer.  A number of customer nodes can be  processed simultaneously
by forking more than one Customer Node child process. If the BGP is configured
to spawn Service child processes, the services within the node are processed
in SERVICE_HISTORY.BILLING_PRIORITY order. Once a Customer Node child process
has completed processing the current hierarchy pass of a customer node it
notifies the parent process by returning a completion message.  The parent
process then sends a message back to the child informing it to either start
processing the next customer node or process the next hierarchy pass of a
customer node it processed earlier.

Customer Node processes are forked at the start of a bill run and remain alive
for the duration of the run. If multiple customers are being processed then
the child process will not terminate until after the last customer is finished
being processed.

### Service Child Process

A Service child process processes one or more services associated with a
customer.  A number of services can be  processed simultaneously by forking
more than one Service child process.  Once a Service child process has
completed processing the current hierarchy pass of a service it notifies the
parent process by returning a completion message.  The parent process then
sends a message back to the child informing it to either start processing the
next service or process the next hierarchy pass of a service it processed
earlier.

Service processes are forked at the start of a bill run and remain alive for
the duration of the run. If multiple customers are being processed then the
child process will not terminate until after the last customer is finished
being processed.

### Event Child Process

As mentioned earlier, event processes allow a service to be billed over a
specified number of processes. This provides scalability when processing large
volume services. Event processes behave in the same way as service processes
except that they only process a service's events within a specified date
range.

Event processes are spawned (forked and exec'd) from the higher level process
when they are first required and remain alive for the duration of the bill
run. If not all higher level processes require the use of event level children
(i.e there are less high volume services than service level processes) this
can result in significantly less processes being spawned for a bill run. This
allows event level children to be configured to be used without the penalty of
the memory use overhead to spawn them unnecessarily.

It is the responsibility of the parent process to calculate the date range and
pass it, along with the service id, to the event process. To calculate the
date range the parent process first finds the minimum charge date for any
charge associated with an event on the service. The entire date range for the
service then goes from the minimum charge date to the effective date of the
bill run. The first start date range to be allocated to an event process is
from the minimum charge date to the minimum charge date plus the EVENT_PERIOD.
Subsequent date ranges go from the previous end date plus one second to the
new start date plus the EVENT_PERIOD. This process continues until an end date
is found that is greater than the effective date of the bill run, this
signifies the last date range to be processed for the service. The last date
range's end date is always the effective date of the bill run. When date
ranges are calculated they are sent to the event process (as they become
available) along with the service id in an IPC message.

When the ipc message is received the event process bills all events and their
charges within the date range to the service and updates all necessary
variable values. When processing is complete the variable values are returned
to the parent process for aggregation and the process is ready to accept
another service, date range combination for processing. This continues until
all necessary date ranges are processed for the service.

Even though event processes exist, they may not be used to process a service
if the event process's parent process determines that the service should not
be split up. If this happens it will be processed entirely in the parent
process.

  * If the total number of events to be processed for the service is less than the value of the SERVICE_MIN_EVENTS attribute in the BGP's configuration item, all processing for the service is done in the parent process.   

  * The BGP may decide that there is no value in using the event processes. Typically this decision will be taken for one of the following reasons:  

    1. If the earliest charge start date to be processed for the service falls within the date range of the effective date of the bill run and the effective date of the bill run minus the value of the EVENT_PERIOD attribute, all processing for the service is done in the parent process. The reason for this is that this scenario would see the entire service processed by a single event process so there is no value to be gained from delegating the processing to a child process.  
  
In this scenario it is possible for the number of events on a service to
exceed SERVICE_MIN_EVENTS but for the event processes not to be used. If this
happens, a warning message will be written to the system log and processing
will be done in the parent.  

    2. Event processes are not used if a progressive subtotal dependency is detected that will cause serialisation of event processing. It is incumbent upon the system configurers to run biInvoiceExplainPlan$(...) to ensure that this situation is avoided for high usage services. If this scenario does occur, no warning message is logged but all processing is done in the parent for the pass in which the progressive subtotal is active. For more information on how progressive subtotals affect parallelism see Progressive Subtotals.

### Multiple Hierarchy Passes

The parent process keeps track of the entities each Customer Node or Service
child process processed during the first hierarchy pass.  During the second
and subsequent passes the parent process assigns the same entities to each
child process as it did in the first pass.   This is done to ensure later
hierarchy passes have access to variable values calculated in earlier passes.

### Parallel Processing

The BGP achieves maximum throughput when all child processes are in use 100%
of the time.  Depending on the customer configuration, this is not always
possible.   Listed below are a number of factors that can cause a child
processes to become idle and therefore increase the overall processing time of
the BGP.

  * Entity processing time.
  * Progressive subtotals.
  * Aggregate subtotals.
  * Invoicing nodes.

#### Entity Processing Time

If an entity takes substantially longer to process than the other entities,
then the child processes processing the other entities will become idle as
they wait for the slow entity to be processed.  The processing time of an
entity can be affected by the following factors:

  * Number of charges associated with an entity (lop-sided customer hierarchy tree).
  * Number of child entities associated with an entity (lop-side customer hierarchy tree).
  * Number of valid tariffs and subtotals associated with an entity.
  * Processing time of expressions associated with an entity.  For example, calling a remote function will greatly increase the processing time of an entity.
  * The number of hierarchy passes required to process the entity.

#### Progressive Subtotals

A valid variable that directly or indirectly depends on a progressive (or _Use
subtotal before final value_) subtotal may cause the hierarchy pass containing
the variable to be processed sequentially for each entity.  To cause
sequential processing, the variable must also have the following
characteristics:

  * Have a context equal to or lower than the child process context.
  * Be evaluated before the progressive subtotal.
  * Depend on a progressive subtotal with a context higher than the child process context.

Figure ?: Example configuration causing sequential processing

Variables matching this description cause the hierarchy pass containing the
variable to be processed sequentially for each entity.  In the following
diagram, the BGP is configured to have two child processes processing two
different entities.  Both children are able to process the first hierarchy
pass at the same time but must process the second pass sequentially.  The
second child process becomes idle as it waits for the first child to process
the hierarchy pass then the first child becomes idle as it waits for the
second child to process the same hierarchy pass.

Figure ?: Sequential processing caused by progressive subtotals.

#### Aggregate Subtotals

A customer node hierarchy pass containing aggregate (or _include amounts from
child nodes_) subtotals must be processed by the child customer nodes before
the parent customer node.  This is done because the value of the subtotal for
the parent customer node depends on the value of the subtotal for each child
customer node.   A number of Customer Node child processes may become idle as
they wait for the other child processes to finish processing their customer
node.  Aggregate subtotals may cause a customer with a narrower customer node
hierarchy tree to have a longer processing time than a customer with a
wider/flatter customer node hierarchy tree.

#### Invoicing Nodes

A customer node with a reporting level of _invoicing_ cannot be processed
until all child customer nodes with a reporting level of _statement_ or _no
reporting_ are processed.  This is done because the invoice amount of an
_invoicing_ node depends on the statement amount of all _non-invoicing_ child
nodes.  _Invoicing_ nodes with _non-invoicing_ child nodes may cause a
customer with a narrower customer node hierarchy tree to have a longer
processing times than a customer with a wider/flatter customer node hierarchy
tree.

Return to contents.

### Statistics

BGP Statistics are available from two places in CB. Firstly, function
biInvoiceGenerate&() creates a hash of statistics that is returned in
parameter 'Statistics'. These statistics are gathered over the whole
biInvoiceGenerate&() call.

The other place that statistics are available is the TRE Monitor. The former
statistics are discussed elsewhere in this document, therefore the remainder
of this section only discusses the statistics that are periodically logged in
the TRE Monitor.

The statistics are gathered via the EPM call-back function BGPStats?{}(). The
statistics that this function returns depend on where it is called. If the
function is called in the parent process, a hash of cumulative statistics
gathered since boot time are returned (See function BGPStats?{}()). A subset
of these statistics gathered by a specific child process is returned if the
function is called in a child process. Once the statistics have been gathered,
a call to biTREServerMonitor&() logs the statistics in the TRE Monitor.

Configuration attributes determine how and how often the statistics are logged
in the TRE Monitor. The configuration attribute STATISTICS_TIMEOUT determines
how often statistics are logged. Each BGP process keeps a record of when
statistics were last logged. In the main loop of processing, if
STATISTICS_TIMEOUT seconds have passed since this particular process last
logged statistics, a function is called to log the current statistics in the
TRE Monitor.  If in multi process mode, each child process keeps its own
record of when it's statistics were last logged and in the main loop of
processing, determines if it needs to log it's statistics in the TRE Monitor.

The actual function that is called in the main loop of the BGP, and by the
child processes, is determined by the STATISTICS_FUNCTION configuration
attribute. This function is configurable and defaults to BGPLogStatistics&().

The BGP also supports the collection of TRE and EPM statistics.  As of version
9.00.07, the BGP adds entries to the EPM call stack for SQL operations as well
as entries indicating the current context it is evaluating.   Refer to the
9.00 Architecture Overview for further details on SQL call stack entries.  The
following call stack entries are added for the BGP processing contexts:

**Call Stack Entry** | **Description**  
---|---  
BGP: Customer | Evaluating customer context variables  
BGP: Customer Node | Evaluating customer node context variables  
BGP: Invoice | Evaluating invoice type expressions  
BGP: Service | Evaluating service context variables  
BGP: Normalised Event | Evaluating normalised event context variables  
BGP: Charge | Evaluating charge context variables  
  
These call stack entries are added to each entity's EPM parser prior to
evaluating each range of variables for that entity.  They are removed on
completion of each range.  Hence the number of calls associated with these
call stack entries in any collected statistics will typically be significantly
greater than the actual number of entities processed in each context.  The
elapsed time for these call stack entries represents the total elapsed time
the BGP has spent evaluating variables in each context.  If EPM  call graph
statistics are collected for the BGP, then any functions and SQL performed as
part of evaluating each range of variables will appear nested under these call
stack entries in the call graph report produced by getstats.

[Contents]

* * *

### Commit Points

The frequency at which the BGP commits records to the database is determined
by the level of multi-processing that it is configured for.  In single process
mode or customer level multi-processing, the BGP commits records to the
database when each root node is unlocked.  Also if during processing, any
table has 1000 outstanding records, all outstanding records are committed
(with a single commit).

In all other levels of multi-processing the BGP commits as follows:

1\. After processing each root node or on a root node error.  
2\. On a bill run failure after all customer node locks are released.  
3\. After each root node is locked.  
4\. After each root node is unlocked.  
5\. After each node is loaded if it is not the first pass.  
6\. Whenever a child process detects an erred customer.  
7\. Each time a child process responds to a parent process's request message.  
8\. During processing - when any table has 1000 outstanding records, all
tables are committed.

[Contents]

* * *

## Multiple Currencies

The BGP processes charges that are aggregated to various totals that are
stored in the INVOICE table such as the invoice total, statement total, a
total for each receivable type, payment total, adjustment total etc. These
totals are calculated in the currency of the customer's account, however the
charges that make up these totals are not always in the same currency so in
some cases the BGP needs to convert charges to the currency associated with
the customer's account.

The BGP has a class called CurrencyAggregator that handles the aggregation of
charges.  As charges are processed and added to the CurrencyAggregator, the
amount is added to the total for that currency.  In this way each
CurrencyAggregator keeps track of a number of currency totals.  When all
processing has finished and the total amount of the CurrencyAggregator is
being calculated, each currency total is converted to the currency of the
account and a grand total calculated.  The date used in the currency
conversion is the bill run effective date.

[Contents]

* * *

## CB 6.00 Partitioning Changes

To work with the multi-column range partitioning model used in CB 6.00, all
queries in the BGP that query the CHARGE table have been modified so that:

  * The query is restricted to charges with the the same PARTITION_NR as the customer node currently being processed.
  * Any queries that join the CHARGE and NORMALISED_EVENT tables include the constraint:  
NORMALISED_EVENT.PARTITION_NR = CHARGE.NORMALISED_EVENT_PARTITION_NR

These two constraints should allow ORACLE to perform partition elimination on
all the BGP queries that access the CHARGE and NORMALISED_EVENT tables,
improving the performance and scalability of the BGP.

Since the PARTITION_NR column in the CHARGE table is derived from the
ACCOUNT_ID of the charge, an implicit assumption made by the BGP is that all
accounts associated with a customer node must be in the same partition as the
customer node itself.  Note that the BGP supports different customer nodes in
a customer hierarchy to being in different partitions, and also for services
being in a different partition to its customer node.

When inserting charges and invoices, the BGP inserts them into the same
partition as the customer node currently being processed.

For an inter-hierarchy and inter-partition charge redirection from the BGP
tariff evaluation, the charge will be inserted to the destination or nominated
account's partition.

In a multi-instance setup, regardless of whether multiple Customer Partitions
are assigned to the same SV server (Single Instance) or each Customer
Partition is assigned to a separate SV server (Multi Instance), and
irrespective of which node the partition of the 'To Account' resides on, the
BGP will forward this inter-hierarchy redirected charge successfully.

[Contents]



* * *

## Signals

The following signals are handled by the BGP:

SIGCHLD

    Records the details of the child process that died and logs a warning message if the child process terminated abnormally.  If the signal was not expected (ie. the child had not been instructed to terminate) and the process receiving the signal is not the parent trebgp process, signals all remaining children to terminate and then terminates itself. Otherwise, if the unexpected signal is received by the parent trebgp process, logs an error for the customer node the child was  processing at the time it terminated, and continues processing the remaining customers in the bill run. The child that terminated is later recreated.
SIGPIPE

    See SIGCHLD
SIGTERM

    If received by the parent trebgp process while processing a biInvoiceGenerate& call, terminates all children by sending them a SIGTERM signal and then immediately returns from the biInvoiceGenerate& call.  Otherwise shuts down any remaining children processes and terminates itself.
SIGINT

    See SIGTERM
SIGUSR1

    Dumps a memory report to the $ATA_DATA_SERVER_LOG directory with the name bgp.<pid>.mem. If the file doesn't exist, it is created, otherwise a memory dump is appended to the end of the file.
SIGUSR2

    Toggles BGP tracing.

[Contents]

* * *

## Financial Reporting Capabilities

    Overview
    GL Codes
            Simple GL Code Allocation
            CB 6.01 GL Guidance
                    GL Guidance Function
                    Implementation
                    Example
    Receivable Types
            Simple Split Receivables
                    Receivable Types and Non Billable Charges
                    Receivable Type Aggregation
                    Rules For Receivable Types
            CB 6.01 Receivable Types
                    Invoice Receivable Type Tables
                    Example

### Overview

Prior to CB 6.01 charges were tagged with GL codes and receivable type ids via
tariff and subtotal configuration.  The receivable types were aggregated per
node resulting in the invoice amount being distributed over several receivable
types.  CB 6.01 introduced a more comprehensive financial reporting system
capable of associating multiple GL codes and receivable types with charges.

To control which financial system is in use, the BGP calls function
GLEnabled&() which in turn queries the reference type GL_ENABLED. By default
this is set to TRUE, however to disable the 6.01 financial system and make the
BGP fully backwards compatible, this reference type can be set to FALSE.

More information can be found in the General Ledger functionality Overview.

### GL codes

#### Simple GL Code Allocation

Prior to CB 6.01 GL codes were assigned to charges based on tariff and
subtotal configuration.  Each tariff and subtotal can optionally define a _to_
and _from_ GL code either via a charge category or on the tariff or subtotal
itself.  (see GL Codes in the tariff section).  Any charges generated by these
tariffs and subtotals will be populated with the GL code specified.

To invoke this method of GL code allocation, the reference type GL_ENABLED
should be set to FALSE.

#### CB 6.01 GL Guidance

As of version 6.01 CB has the capability of assigning multiple GL codes per
charge.  Instead of assigning GL codes through tariff and subtotal
configuration, charges are associated with GL codes via GL Guidance Entities.
A GL guidance entity defines GL codes for crediting and debiting Earned But
Unbilled (EBUB), Billed and Earned (BE) and Billed But Unearned (BUE) amounts
to associated accounts.

The function GLGuidance?[] is called once for all unsuppressed charges
processed or generated by the BGP that are associated with billable tariffs.
That is all of the following:

  1. All rating charges processed by the BGP generated from billable tariffs
  2. All charges generated by the BGP itself from billable tariffs
  3. All transferred billable charges generated by another BGP process 

The function is only called for unsuppressed charges associated with billable
tariffs. It is not called for charges associated with subtotals and non-
billable tariffs, and it is not called for suppressed charges ie. zero value
charges with "Suppress zero?" checked.

The GL Guidance mappings are aggregated for each node.  Non-invoice level
nodes have their GL guidance aggregations passed up the hierarchy to the
nearest invoice level node.  Essentially all nodes that have an invoice
generated will also have a GL Guidance breakdown of that invoice inserted into
the database.

The aggregated GL guidance mappings for each invoice level node is stored in
the INVOICE_GL_GUIDANCE table.  This information is used by the sales journal
posting script.

#### GL Guidance Function

The contents of this function depend on the implementation requirements, but
the purpose is to return an array of GL Guidance entities that the charge maps
to.  The function returns an array of unknown hashes. Each hash must have the
following keys of the correct type.

Key | Type | Description  
---|---|---  
GL_GUIDANCE_ID | Integer | Unique identifier of the GL Guidance entity  
AMOUNT | Real | Amount allocated to this GL Guidance entity  
CURRENCY_ID | Integer | Currency of the amount  
START_DATE | Date | (Optional) Start date and time of period over which amount applies  
END_DATE | Date | (Optional) End date and time of period over which amount applies  
  
The Start and End dates are specified for rental charges. The date range is
for proportioning the amount between BUE and BE GL codes (for advance
rentals).

The following validation is performed on the results of the GLGuidance?[]
function:

  1. At least one GL guidance mapping must be returned if the charge is non zero
  2. If the account to which the charge is directed is an AR (Accounts Receivable) account, then 
    1. For rating and rental charges: 
       * For EBUB to BE (ie. Accrual) GL guidance entities:
         * All returned GL Guidance entity rows with AR GL codes must be in the currency of the charge
         * The GL Guidance EBUB currency must match the currency of the charge
       * For all non-Accrual GL guidance entities, all returned GL guidance entity rows with AR GL codes must be in the currency of the account
       * If the GL guidance entity has BE GL codes specified and the charge currency doesn't match the account currency, then the charge and GL guidance amounts are converted to the account currency before validation for the current charge. Note that charge and GL guidance currencies must still comply with the validation rules, however they are converted to the account currency before being summed and compared 
    2. For charges generated by the biller all returned GL Guidance entity rows with AR GL codes must be in the currency of the account 
    3. The total debits to AR BE (Billed and Earned) GL codes returned must equal the amount of the charge (after the charge has been converted to the currency of the account.)
    4. For returned GL Guidance entities with AR GL codes:
       * The currency of the GL guidance entity must match the currency of the account
       * The GL guidance entity must have a corresponding receivable type. The currency of that receivable type must match the currency of the account.  Note that the receivable type currency is implied from the GL code it is associated with (see CB 6.01 Receivable Types for more information)
  3. If the account to which the charge is directed is _not_ an AR account, then the net amount debited to AR BE GL codes must be zero 
  4. If the charge is generated by the biller, GL Guidance entities returned must not have EBUB GL codes specified
  5. If the GL guidance row has START_DATE and END_DATE specified then the corresponding GL guidance entity must have EBUB GL codes or it must have BUE GL codes.  If the corresponding GL guidance entity has EBUB GL codes specified then START_DATE and END_DATE are ignored and the GL guidance mappings are aggregated like a standard EBUB to BE usage charge.
  6. If the GL guidance entity returned in the GL guidance row has an EBUB component, then the GL guidance row's currency must match the GL guidance entity EBUB currency; otherwise, it must match the GL guidance entity currency

Furthermore, GL guidance mappings returned from GLGuidance?[] that match one
of the following criteria are ignored by the BGP:

  1. Charges generated by the rater; _and either_  

     * Include GL Guidance entities with only BUE and BE GL codes specified (ie. Deferral GL guidance entities) _or_
     * Include GL Guidance entities with only EBUB GL codes specified (ie. Non-billable Gl guidance entities) 
  2. Charges generated by the RGP and include GL guidance entities with only EBUB GL codes specified (ie. Non-billable GL guidance entities) 

GL guidance mappings matching these criteria are ignored by the BGP because
they represent transactions that have no Accounts Receivable impact.  For more
information see GL Guidance Processing Overview.

It is a requirement that the GL guidance function (GLGuidance?[]) return the
same result for a charge whether called during rating or billing. Therefore
the function is called with an effective date of the charge start date for
rating charges (and the bill run effective date for billing charges).
Furthermore the variables available during evaluation are defined explicitly:
the function has access to all variables associated with the CHARGE_INPUT_V
and NORMALISED_EVENT_V.

For bgp generated charges above the event context the NORMALISED_EVENT_V
variables will be undefined. There are also some special direct variables
associated with the CHARGE_INPUT_V view that do not correspond directly to
fields in that view (see Special Direct Variables).

#### Implementation

As each charge is processed, the details of the charge are stored in a
ChargeDetails object.  This class stores details such as the charge amount and
currency as well as the account and node the charge is directed to.  The class
also contains a FinanceDetails object which stores the finance reporting
details (either its GL Guidance breakdown or its associated receivable type).
If CB is configured to use the pre-6.01 finance system, this object will
simply contain the receivable type id associated with the charge, otherwise
GLGuidance?[] is called and the resulting array of GL Guidance mappings are
stored in a GLGuidanceContainer object within the FinanceDetails object.

When validating the results of GLGuidance?[] the BGP accesses the General
Ledger Cache (GLC) for retrieving GL code and GL guidance entity details.

As the charge is added to the message to pass up to the correct node, a check
is made to determine if there is already a charge in the message to combine
the new charge with.  If the BGP is using the pre-6.01 finance system a
'match' occurs if the AccountId, CurrencyId, ReceivableTypeId are identical
and the charges have the same 'Billable' status (ie. both charges are
'billable' or both charges are 'non billable').  If the BGP is using the 6.01
finance system the AccountId, CurrencyId and Billable status must match in
order for the charges to be combined.

Combining the charges is simply a matter of adding the amount of the second
charge onto the first and combining the GL Guidance aggregations (if
applicable).

When the charge reaches the account and node it is directed to, the charge is
added to the invoice amount. If the charge has an associated receivable type,
it is also added to the ReceivableTypeContainer that keeps totals for each
receivable type directed to this Account. If the charge has associated GL
Guidance mappings, they are added to the account's GLGuidanceContainer which
keeps track of the GL Guidance totals of the charges directed to this account.

When the invoice details are inserted into the INVOICE table, the
INVOICE_GL_GUIDANCE table is also populated for invoice level accounts with
the aggregated GL Guidance details stored in the account's
GLGuidanceContainer.

#### Example

The following charges are invoiced in a bill run with effective date 01-FEB
2005

Type | Charge Id | Charge | Charge Start Date | Period Start Date | Period End Date  
---|---|---|---|---|---  
Usage | USG_01 | $5.00 | 01-JAN-2005 09:01:05  |   |    
Usage  | USG_02 | $1.00 | 02-JAN-2005 11:23:12  |   |    
Usage | USG_03 | £2.00 | 02-JAN-2005 13:05:00  |   |    
Recurring | REC_01 | $20.00 | 01-FEB-2005 00:00:00 | 01-JAN-2005 00:00:00 | 28-FEB-2005 23:59:59   
Billing | BILL_01 | $5.00 |   |   |    
  
On the first pass to the charge context, when charges are retrieved from the
database and read in by the BGP, the function GLGuidance?[] will be called for
each billable charge.  Some charges map to several GL guidance entities ie.
there is a tax component and a usage component to the charge.  GLGuidance?[]
is also called for each charge that the BGP generates itself.

The above charges map to the following GL Guidance entities:

Charge | GL Guidance Entity | Amount | Currency | Period Start Date | Period End Date  
---|---|---|---|---|---  
USG_01 | GL_GE_USG_AUD | $4.50 | AUD |   |    
GL_GE_TAX_AUD | $0.50 | AUD |   |    
USG_02 | GL_GE_USG_AUD | $0.90 | AUD |   |    
GL_GE_TAX_AUD | $0.10 | AUD |   |    
USG_03 | GL_GE_USG_GBP | £1.40 | GBP |   |    
GL_GE_TAX_GBP | £0.60 | GBP |   |    
REC_01 | GL_GE_RECURRING | $20.00 | AUD | 01-JAN-2005 00:00:00 | 28-FEB-2005 23:59:59  
BIL_01 | GL_GE_BILLING | $5.00 | AUD |   |    
  
Because REC_01 is a rental charge with part of its charge period in advance,
the GL guidance entity mapping has a date range for proportioning the amount
between Billed and Unearned (BUE) and Billed and Earned (BE).

In this example all charges are directed to the same customer node and
account.  After the customer has been processed and the invoice total details
are inserted into the database, the aggregated GL Guidance details are stored
in the INVOICE_GL_GUIDANCE table.  The invoice currency is $AUD.

Sequence | GL Guidance entity | Period Start Date | Period End Date | EBUB Amount | Amount  
---|---|---|---|---|---  
1 | GL_GE_USG_AUD |   |   | $5.40 | $5.40  
2 | GL_GE_TAX_AUD |   |   | $0.60 | $0.60  
3 | GL_GE_USG_GBP |   |   | £1.40 | $3.30  
4 | GL_GE_TAX_GBP |   |   | £0.60 | $1.40  
5 | GL_GE_RECURRING | 01-JAN-2005 00:00:00 | 28-FEB-2005 23:59:59 | $0.0 | $20.00  
6 | GL_GE_BILLING |   |   | $0.0 | $5.00  
  
### Receivable types

CB's split receivable system allows the amount on an invoice to be divided
among a number of Receivable Types. These Receivable Types may be loosely
viewed as buckets of money that give a breakdown of the amount of an invoice,
often in terms of money owed to other suppliers, departments, or government
agencies.  Receivable Types are the mechanism for allocating partial payments
to invoice amounts. Allocating different receivable types priorities is a
typical way in which these allocations are performed, how and if the
priorities are used is dependent on the payment/invoice allocation algorithm
chosen.

For example, if it is a legislative requirement that the GST component is paid
before any money is directed to to the service provider and if the service
provider has determined that the margin on calls within its own network is
greater that on calls on resold services then the following Receivable Types
may result.

  1. GST_RX_TYPE priority 1.
  2. INTERNAL_CALL_RX_TYPE priority 2.
  3. RESOLD_CALL_RX_TYPE priority 3.

All invoice level nodes whose prime account is an 'Accounts Receivable'
account have an invoice receivable type breakdown inserted into the database.

The invoice amount will be allocated out over several receivable types. When
any payments or adjustments are made to this invoice, taxes will be payed
first, followed by internal calls followed by resold calls.

CB has two ways of allocating amounts to receivable types: simple split
receivable type allocation and receivable type allocation as part of the CB
6.01 financial reporting capabilities.

#### Simple Split Receivables

In the pre-6.01 system, receivable types are associated with tariffs and
subtotals and any charges generated will be associated with the corresponding
receivable type.  Eg. using the receivable types defined above, when the BGP
detects a GST charge, it is allocated to the GST_RX_TYPE receivable type. When
the BGP detects a call that originated and terminated inside the service
provider's own network then charges from these calls are given a receivable
type of INTERNAL_CALL_RX_TYPE. When the BGP detects a call with a resold
component the charges from these calls are allocated the RESOLD_CALL_RX_TYPE
receivable type.  At the same time the invoice total is generated, the
receivable types are totaled and stored in the INVOICE_RECEIVABLE_TYPE table.

As a result of this, when a customer pays an invoice, all GST is paid first
followed by internal calls and lastly followed by resold calls. If the
customer chooses to partially pay an invoice then invoiced items are paid off
in order of receivable type priority, ie. GST_RX_TYPE charges followed by
INTERNAL_CALL_RX_TYPE charges followed by RESOLD_CALL_RX_TYPE charges.

If the system is using receivable types then there will always be a system
wide default receivable type. This is used to balance any discrepancy between
the total amount aggregated against receivable types for an account, and the
invoiced amount for the account. The balancing of aggregated receivable amount
and invoiced amount takes the form of an additional record written to the
INVOICE_RECEIVABLE_TYPE table against the default receivable type for the
difference. At start-up the BGP looks for a default receivable type. If a
default is found then the system is considered to be using receivable types,
if no default is found then all receivable types are ignored and no
aggregation is performed.

##### Receivable Types and Nonbillable Charges.

Non-billable charges are allowed to be aggregated according to their
receivable types because billable charges may not provide a fine enough level
of granularity of receivable types on the invoice. In this case variables that
produce non-billable charges may be configured to produce receivable types
against these charges in order to increase the granularity of receivable type
aggregation.

Non billable charges will be aggregated into a Receivable Type for a specific
account if the variable that generates the charge supplies a receivable type
for it. In this case the charge is given a billing status of non-billable and
sent to the account for aggregation. The system default receivable type is
never applied to a non billable charge. Thus, if a variable that generates a
non-billable charge (subtotal, non-billable tariff) does not supply a
receivable type for the charge then the charge is not aggregated.

##### Receivable Type Aggregation.

Receivable Type aggregation is only performed for invoice nodes and then only
for the prime account of that node. This is due to the fact that it is only
these accounts for which invoices are generated and therefore only these
accounts which invoiced payments can be made against. If at any time a charge
is added to a statement or report node, then the charge is added to the node's
statement and then transferred up the hierarchy to the closest invoice node
where it is aggregated according to its receivable type.

Within the BGP, the aggregation of charges to receivable types may occur at
two levels.

  1. Whenever a charge is placed into the ChargeList of a ContextMessage object a search is made through the list for another charge with the same Account Id and same Receivable Type Id and the same billing status. If such a charge is found, the new charge is simply added to the existing charge and no new entry is made in the ChargeList. If no charge is found with the same Account Id, Receivable Type and billing status then the new charge is added to the ChargeList.  
  
At this level of aggregation the difference in the billing status of the
charge is significant since billable charges must be added to the invoice
amount when the charge reaches the destination account and non-billable
charges must not be added to the invoice amount.  

  2. When charges reach the destination account, they are aggregated without regard to Account Id (it should be the same account) or billing status but according to their Receivable Type only. The billing status is used at this point to calculate the invoice amount but not for aggregating against a receivable type. This final stage of aggregation is in preparation for populating the INVOICE_RECEIVABLE_TYPE table which contains a breakdown of the accounts invoices charges and receivable types.

##### Rules for Receivable Types.

The following are the rules that the BGP uses to aggregate receivable types:

  * If there is no system default receivable type then all receivable types are ignored for the bill run and no aggregation is performed.  

  * If a system default receivable type is detected for the effective date of the bill run then the following rules will apply:  
  
1\. Receivable Types may only be aggregated for the prime accounts of invoice
nodes  
  
2\. If a charge is directed to a statement or reporting node then it must be
transferred to the nearest invoicing node in the hierarchy for Receivable Type
aggregation.  
  
3\. If a billable charge has no receivable type. In this case the charge is
not aggregated into any receivable type at the account but is simply added to
the invoice amount.  
  
4\. If a billable charge has a receivable type then this is the receivable
type used for aggregation.  
  
5\. If a non billable charge has a receivable type then the charge is directed
to the appropriate account and aggregated into this receivable type. The
charge will otherwise not affect the invoice details.  
  
6\. If a non billable charge has no receivable type it is neither sent to an
account nor aggregated.  
  
7\. When an invoice is generated, if there is a difference between the total
of all charges aggregated into all receivable types for the account and the
invoice amount the BGP will balance the books by creating an additional record
in the INVOICE_RECEIVABLE_TYPE table to make up the difference. This
additional record will be created against the system default receivable type.  
  
8\. The INVOICE_RECEIVABLE_TYPE table may only be populated at the time a
node's INVOICE record is committed to the database.

#### CB 6.01 Receivable Types

The financial reporting system introduced in CB 6.01 includes a new form of
receivable type aggregation. As described above, all non-zero billable charges
map to at least one GL Guidance entity via the function GLGuidance?[].  A GL
guidance entity can be associated with a receivable type via an 'Accounts
Receivable' GL code.

Either the BE Credit or BE Debit GL code can be an 'Accounts Receivable' GL
code (see the GL_GUIDANCE_HISTORY table model).  The table model also enforces
that each receivable type be associated with an 'Accounts Receivable' GL code
ie. GL_CODE_ID is mandatory and unique in the RECEIVABLE_TYPE_HISTORY table
(if the 6.01 financial system is in use).

Therefore GL guidance entities are associated with receivable types via one of
the BE GL codes (however the table model does not enforce this for all GL
guidance entities).   This association is summarised in the following diagram.

To determine the receivable type associated with a GL guidance entity (if
any), the BGP retrieves GL guidance entity details from the General Ledger
Cache (GLC) and determines if either of the BE debit or BE credit GL codes is
an 'Accounts Receivable' GL code. If so, it then retrieves the corresponding
GL code.  If the GL code has an associated receivable type, then this GL
guidance amount contributes to the receivable type totals for the node the
charge is directed to.

The BGP aggregates these receivable types for each node.  All invoice level
nodes whose prime account is an 'Accounts Receivable' account have an invoice
receivable type breakdown inserted into the database. Other nodes have their
receivable type breakdown passed up the hierarchy to the next invoice level
node (along with the GL guidance mappings).  Therefore some accounts will
receive an invoice but no receivable type breakdown.

##### Invoice Receivable Type Tables

The aggregated receivable type totals are stored in the following invoice
receivable type tables:

INVOICE_RECEIVABLE_TYPE

    Contains a row for each receivable type portion of an invoice.  Each row contains the invoice id, receivable type id, amount and current due for each receivable type portion of the invoice.
INVOICE_HISTORY

    Contains the same data however each row also contains a date range so that as payments and adjustments are made against the invoice over time, the remaining current due can be retrieved for each receivable type total.  For this reason the table stores both a 'Previous Due' and 'Current Due' to store the amount due before and after the transaction respectively.
     
    The initial rows inserted will have a date range from the invoice issue date until the end of time.

##### Example

Continuing the example earlier, the charges invoiced in the 01-FEB-2005 bill
run map to the following GL Guidance Entities and Receivable Types:

Charge | GL Guidance Entity | Receivable Type | Amount  
---|---|---|---  
USG_01 | GL_GE_USG_AUD | RX_USAGE | $4.50  
GL_GE_TAX_AUD | RX_TAX | $0.50  
USG_02 | GL_GE_USG_AUD | RX_USAGE | $0.90  
GL_GE_TAX_AUD | RX_TAX | $0.10  
USG_03 | GL_GE_USG_GBP | RX_USAGE | $3.30  
GL_GE_TAX_GBP | RX_TAX | $1.40  
REC_01 | GL_GE_RECURRING | RX_ADVANCE | $20.00  
BIL_01 | GL_GE_BILLING | RX_USAGE | $5.00  
  
These receivable types are aggregated and inserted into the INVOICE_HISTORY
table:

Receivable Type | Amount | Current Due | Effective Start date | Effective End Date  
---|---|---|---|---  
RX_USAGE | $13.70 | $13.70 | 01-FEB-2005 | EOT  
RX_TAX | $2.00 | $2.00 | 01-FEB-2005 | EOT  
RX_ADVANCE | $20.00 | $20.00 | 01-FEB-2005 | EOT  
  
As payments and adjustments are made against the invoice, certain receivable
types will be paid off before others and new date ranged records will be
inserted into INVOICE_HISTORY with the new 'Current Due' amounts.

#### Corrective Rounding

In CB 6.01, receivable types are set from their GL Guidance amounts. GL
guidance amounts are specified in full charge precision, but receivable type
must be rounded to currency precision when stored. As the total of each
rounded receivable type amount must equal the rounded invoice total, under
certain conditions this may cause a discrepancy between the totals. For
example, given the receivable type amounts:

Un-rounded Amount | Rounded Amount  
---|---  
$10.243 | $10.24  
$10.244 | $10.24*  
$10.113 | $10.11  
**$30.60** | **$30.59**  
  
Under these conditions, the rounded receivable amounts are adjusted by the
currency scale amount until the total is equal to the rounded invoice total.
The most ideal candidates for the adjustments are used, such that the
difference between the new rounded amount and the un-rounded amount is
minimised. In the above example, the '$10.24' amount, with an original un-
rounded amount of '$10.244' would be rounded up to '$10.25'.

GL Guidance amounts associated with receivable types for A/R accounts are
rounded to currency precision for storage to INVOICE_GL_GUIDANCE. The
corrective rounding algorithm is also applied to these GL Guidance amounts to
ensure they sum to the respective (potentially adjusted) receivable type
amount. Both the currency rounding and rounding correction is performed to
ensure the A/R GL amounts sum to the receivable type amounts, which in turn
sum to the invoice total.

* * *

## Large Customer Hierarchies

Processing a customer hierarchy involves processing all customer nodes,
services, events and charges in that hierarchy and evaluating all associated
variables at various contexts (see Context Processing). Depending on the
variable evaluation order, each context may be visited several times for the
same entity. For this reason, entities are cached within the BGP for the
persistent contexts (Customer, Customer Node, Service). The non-persistent
contexts (Normalised Event, Charge) are not cached and therefore have to be
read back in for each pass.

A persistent context entity is kept in BGP memory as long as it is needed.
Services are deleted from memory at the end of the last pass to service and
Customer Nodes are delete at the end of the final pass to customer node.
Because of this requirement, a large amount of memory may be required to
process large customer hierarchies. Eg. consider a customer hierarchy with 100
000 services, assuming an average of 100 Kb to store service details, the
hierarchy may require up to 10Gb of memory (or swap space) to process.

The BGP has two configuration options to reduce the total amount of memory
required to process large customer hierarchies :-

  1. Store service details to disk
  2. Exclude idle services

### Store Service Details to Disk

The BGP can be configured to store service details to disk and only keep a
service 'stub' in memory. Once service details are stored, they no longer need
to be kept in memory and can be deleted.  On the next pass to service, the
service details are retrieved from the database and the service is restored
ready for processing again.

This behaviour is controlled by the SERVICE_DETAILS_TO_DISK configuration
attribute. If set to TRUE, service details are encoded and stored in the
database at the end of a pass to service. If set to FALSE, the service details
are cached in memory until the end of the last pass to service.

#### Serialising Data

`The BGPEncoder` class handles the serialising of data into a buffer suitable
for storing in the database. This class is also used to encode data into a
buffer suitable for passing between BGP processes. Any bgp object that will
need to be encoded will inherit from the `BGP_EncodableObject` class and will
have `Encode` and `Decode` data members.

The data that needs to be encoded for a service entity is the following

Data | Class | Module  
---|---|---  
Entity parser, containing the values of all variables for this service | `BuiltinSQLFunctionParser` | EPM/FLM  
Pass order cache key | `MultiProductCombinationKey` | BGP  
The values of running subtotal terms | `ValueDetailsList` | BGP  
  
All of these BGP classes have an `Encode` method which will serialise and
encode the data into the `BGPEncoder` buffer. The variable evaluation order
associated with the service is not encoded, this is kept in a cache and a
pointer to it stored with the `ServiceEntity`.  However the pass order cache
key is encoded so that it is available on subsequent passes.

The entity parser is encoded within `ContextEntity::EncodeParser`.
`Parser::GetVariableCount` is called to get the size of the parser in
variables.  For each variable `Parser::GetVariable` is called with
`l_search_base` set to false as only variables in the entity parser need to be
encoded, not variables from the (shared) base parser.

All of these functions are called from the `ServiceEntity::Encode` method.

#### Storing to Database

The service details need to be written to the database at the end of each
service pass, when control passes above the service context ie. at the end of
`ContextInterface::ProcessContext` when a message is generated for passing up
to the parent context.  Details are only stored to the database if there is
more one pass to service.  If there is only one service pass then the
`ServiceEntity` is deleted at the end of the pass.

After the service details have been serialised into a buffer they are written
to the `SERVICE_BILL_RUN_T` table. Rows are inserted into this table by
`bill_run_operation_id`, `customer_node_id` and `service_id`. Customer node id
is necessary because a single service can belong to more than one customer.
By using Oracle as the cache we get easy indexing capabilities so we can
reload by `service_id`.

Once the service details are encoded and stored in the database
`ContextEntity::Free` is called to delete the entity details that have been
stored in the database, freeing up memory associated with that service and
leaving only a 'stub' in memory.  The pass order cache key, running subtotal
term list and parser are all deleted from memory.  At the end of the last pass
`Context::DeleteEntity` is called instead of `ContextEntity::Free` to
completely remove the entity from the cache as it is no longer needed.

At the end of the first pass to Service, rows are inserted into the database
(as long as it is not also the last pass to service ie. there is more than one
pass to service). At the end of subsequent passes to Service the rows are
updated. At the end of the last pass to service, the rows are deleted.

#### Restoring Service Details

On subsequent passes to service in `ServiceContext::LoadEntity` which is
called from `Context::Init`, if it is not the first pass to service,
`ContextEntity::Restore` is called to recreate the service.  The
`SERVICE_BILL_RUN_T` table is queried for the current `bill_run_operation_id`,
`customer_node_id` and `service_id` and a `ServiceEntity` is decoded from the
data stored in the database.

The `ServiceEntity::Decode` method re-constructs the service details from the
data retrieved from the database by calling the various `Decode` methods for
each of the BGP classes stored in the database.

The entity parser is reconstructed via the `ContextEntity::DecodeParser`
method. For each variable decoded, `Parser::DefineVar` is called to define the
variable in the parser and then `Parser::AssignVar` is called to assign the
value to the variable.

### Exclude Idle Services

The BGP can be configured to automatically exclude services in the hierarchy
that do not contribute to billing; reducing the amount of memory required to
process the hierarchy. This option only provides benefits for large customer
hierarchies where a significant proportion of services are idle.

An idle service is defined as one that does not have any unbilled charges for
the current billing period.  This includes usage charges and rental charges.
Note that in a typical installation a non-cancelled service would usually have
charges generated during rental event generation. To take advantage of this
option rental tariff configuration may need to be modified to ensure that no
rental charges are generated for the idle services.

The service is excluded prior to any billing charges being generated. An idle
service that generates charges at billing time will still be excluded and the
billing charges will not be generated if this mode is enabled. If the
configuration is dependent on billing charges generated in this way then this
mode should not be enabled.

Furthermore, idle services are excluded regardless of their status. Even an
active service will be excluded if it has no unbilled charges. Services that
were cancelled mid way through the billing period and that have usage yet to
be billed will still be processed regardless if this mode is enabled or not.

If a billing tariff transfers a charge to another account in the hierarchy
(known as an intra-hierarchy charge) then the charge is transferred to the
corresponding node and the service is processed under the destination node as
a phantom service. The transfer of this charge ensures that the phantom
service is not classified as idle and excluded from processing. Therefore any
remaining variables to be processed for the phantom service will be evaluated
as expected.

This behaviour is controlled by the EXCLUDE_IDLE_SERVICES configuration
attribute. If set to false (0) then all services are processed regardless of
their unbilled charge count. If set to true (1) then services with no unbilled
charges are excluded as described in this section.

#### Implementation

When this mode is enabled a query is performed when initiating each service
entity to retrieve a count of the number of unbilled charges associated with
that service. If the count is zero and EXCLUDE_IDLE_SERVICES is enabled then
the service is flagged to be excluded from processing. No lower contexts are
processed for this service. The details of the excluded service are added to
the message sent back to the parent context (Customer Node). Service is not
stored in the service cache and any memory allocated to it is freed.

When the message is received by the parent customer node the service id is
stored in a list to keep track of excluded services. On subsequent passes when
the customer node is iterating through and processing its child services, the
list is checked and any excluded services are skipped.

The query to retrieve a count of charges associated with a service is already
performed if the BGP is configured to use event range children, however if
event range children are not configured then this is an extra query performed
per service that would not be executed if this mode were not enabled.

[Contents]

* * *

--------------------------------------------------
## Contents

Overview  
Related Documents  
Section 1 - Using the Server  

Starting the Server  
Configuration  
Services  
Tuxedo Server Functions  
EPM Built-in Functions  
Statistics  

Section 2 - Rental Generation and Adjustment Processing  

Database Integrity  
Retrieving Product/Tariff Details  
Event Generation for Recurring Tariffs  

Calculating the Charge Period  
Determining Active Periods  
Calculating Durations  
Event Splitting  

Bill Run Schedules  

Schedule Repeat Type  
End of Month Billing  

Retrospective Adjustment  

Retrospective Adjustments for Rental Events Generated by Current Bill Run
(Arrears Rentals)  
Retrospective Adjustments for Rental Events Generated by Previous Bill Runs  

Event Generation for One-off Charges  

Activation  
Cancellation  

Interim Mode  
Outputting Events  
Real and QA output  
OO Design  

RGP  
RgpTariffInfo  
RgpGenerator  
RgpEntity  
RgpTimeLineStep  
RgpChargeTime  

Section 3 - Server Multi-process Considerations  

Server Considerations  

Server Class Diagram  
Single Process Sequence Diagram  
Multi-process Server Sequence Diagram  
Multi-process Client Sequence Diagram  

Multi-process Considerations  

Multi-process Class Diagram  
Multi-process Framework Sequence Diagram  
Process Controller Class  
Child Process Class  
Pipe Class  
Message Class  
RGP Controller  
Parent To Child Sequence Diagram  
Parent From Child Sequence Diagram  
Child To Parent Sequence Diagram  
Child From Parent Sequence Diagram  
Number Of Processes  
ENM Mapping  
Multi-tenancy  
Flow of execution  
Termination  
Signals  

  

* * *

## Related Documents

Unit Test Plan  

[Contents]

* * *

## Overview

The RGP is a tuxedo server advertising functions which will generate rental
and adjustment events.  This document is divided into three sections.

Section 1 pertains to using the server. This includes starting and configuring
the server as well as the services offered and the functions each service
implements.

Section 2 pertains to rental and adjustment generation.  It describes the
architecture as well as the methodology the RGP server employs to generate
rentals and adjustment events.

Section 3 deals with server specific architecture.  It details the multi-
process design and how the server interacts with it.

[Contents]

* * *

## Section 1 - Using the Server

The following section contains information about using the server.  This
includes starting the server, configuring the server as well as all of the
server's services and functions.

[Contents]

* * *

## Starting the Server

The server can be invoked with the following command line options:

    
    
        trergp -- <ConfigurationName|ConfigurationSeqNr> [-s]
    
    	eg trergp -- RGP1

The arguments are as follows:

**`<`ConfigurationName|ConfigurationSeqNr`>`**

    This mandatory flag specifies either  Name or Sequence number of the RGP configuration item. This is used for retrieving configuration information. Multiple RGP servers may use the same configuration item.


**`-s` **

    Stand alone mode
    If this optional parameter is specified, then the RGP Server operates in stand alone mode, that is, no messages for the ERB are generated. This means that the events generated by the RGP will be left in data files and not rated. This is primarily intended for unit testing. 

[Contents]

* * *

## Configuration

In addition to command-line arguments, configuration information for the
process is maintained in the database and accessed via the `**attr**` module.
This information is uniquely keyed by the name of the process (`**RGP**`) and
the process id specified on the command line. The following attributes are
currently supported:

The configuration is loaded when the server is booted, and the server must be
re-booted for configuration changes to take effect.

**MAX_EVENTS** (Mandatory)

    This attribute specifies the maximum number of event records to be stored in a single output file. 
**CHILD_PROCESSES** (Optional)

    This attribute specifies the number of child processes the RGP will spawn.  For example, a value of  2 means run with one parent process and two child processes, a value of 1 means one parent process and one child process and a value of 0 means run in single process mode .  When more than one process is specified the parent, does not process tariffs but simply feeds the other child processes with tariffs to process.   This attribute is optional.  If it is not present the RGP runs as if a zero value was specified, (that is in single process mode).
**ENM_PROCESS_LIST **(Mandatory)

    This attribute specifies a list of process numbers of Event Normalisation processes (ENM) that should receive the events generated by this process. It is a comma separated list of positive numbers.  Example: "1,2,3,4".  For more information see ENM Mapping.
**EVENT_SOURCE**  (Mandatory)

    This attribute specifies the event source name to pass to the ENM when delivering event files. Refer to the ENM documentation for details of how the event source name is used. 
**TARIFF_CHECK**  (Mandatory)

    This attribute is a boolean (`**TRUE**` or `**FALSE**`) flag that controls whether product/tariff links are checked when determining the active periods for a product. If `**TRUE**`, no charges will be generated for periods where the associated product/tariff link is inactive. If `**FALSE**` the product/tariff link is ignored. 
**GENERATE_PERIOD** (Optional)

    This attribute specifies the number of days prior to the bill run effective date that the RGP will examine history records of CB entities (product instances, services, equipment items and facility group instances).  For example a value of 90 would mean that entity history records with an effective_end_date greater than or equal to 90 days before the effective date of the bill run would be ignored wrt rental generation. If not specified, the RGP will examine all history records from the date that the entity was previously billed (or the date the entity became active) until the end of time.  By default this attribute does not have a value specified.
**ADJUSTMENT_PERIOD** (Mandatory)

    In the case of retrospective event adjustment, this attribute specifies the number of days prior to the effective date for which rental adjustments are to be made.  
In the case of normal rental event generation, this attribute specified the
number of days prior to the effective date for which one off charges will be
generated.  
For RGP that is configured for generating quote, this attribute specifies the
number of days prior to the quote effective date that the RGP examines the
rental and adjustment charges when generating a quote. For example a value of
90 means that normalised event records with an effective_end_date less than 90
days prior the quote effective date will be ignored. In addition, this is also
used by the zQuoteCustomerDuplicate& function to control the number of entity
history records to duplicate when generating a quote for an existing customer.

**CALL_ERROR_THRESHOLD** (Optional)

    If the number of non-fatal errors for a single TRE call exceeds this threshold, the call fails with an error causing the processing of the bill run to fail. This defaults to a value of zero if not specified.   See Error Handling for more details.
**HIERARCHY_ERROR_THRESHOLD** (Optional)

    If the number of non-fatal errors for a single customer node hierarchy exceed this threshold, the processing of the hierarchy is aborted, and the hierarchy is recorded as having erred. If some errors occur but the number is less than or equal to this threshold, the RGP does not abort the hierarchy. This defaults to a value of zero if not specified.  See Error Handling for more details.


    NOTE: If the number of customer nodes in a hierarchy is less than or equal to this threshold and none of the customers in the hierarchy are processed successfully the hierarchy is recorded as having erred.  


**DEBUG_LEVEL` `**(Optional)

    This attribute sets the initial RGP tracing level. The tracing level may be changed at runtime using the Specifies the level of debugging information. See biTrcRental& function. When turned on, new trace files are created if none are present, and the trace files are opened for appending. One file is created for each process used by the server. The file naming convention for the server (parent) process and child processes are biRental<GroupId>.<ServerId>.P.<processId>.trc and biRental<GroupId>.<ServerId>.C.<ProcessId>.trc respectively. The selected trace level is output to the trace file(s) in the $ATA_DATA_SERVER_LOG directory. The default debug level is None (OFF). 

Mnemonic  | Decimal  | Hexidecimal  | Description   
---|---|---|---  
OFF | 0 | 0x0 | All tracing off (default)  
ORA | 1 | 0x1 | Turn Oracle tracing on  
MEM | 2 | 0x2 | Print MEM report on completion  
RDB | 4 | 0x4 | Database tracing  
CHG | 8 | 0x8 | Charge tracing  
EVT | 16 | 0x10 | Event tracing  
SER | 32 | 0x20 | Service tracing  
EPM | 64 | 0x40 | EPM tracing  
MUL | 128 | 0x80 | Multi-processing details  
DBG | 256 | 0x100 | Debug tracing  
SCT | 512 | 0x200 | Server controller details  
GCT | 1024 | 0x400 | Generator controller details  
TAR | 2048 | 0x800 | Tariff details  
GEN | 4096 | 0x1000 | Generator tracing  
STR | 8192 | 0x2000 | Storage tracing  
CFG | 16384 | 0x4000 | Configuration tracing  
ENT | 32768 | 0x8000 | Entity tracing  
PRP | 65536 | 0x10000 | Process protocol tracing  
PRS | 131072 | 0x20000 | Process status tracing  
PRC | 262144 | 0x40000 | Process controller tracing  
NOD | 524288 | 0x80000 | Node manager tracing  
EPM_LIGHT | 1048576 | 0x100000 | EPM Light tracing (function parameters and return values not included in trace)  
ALL | 2097151 | 0x1FFFFF | All of the above  
  
    The debug level can be specified by using a decimal number eg. 16, or a hexadecimal number eg. 0x10, or a mnemonic eg. "MPP".   Multiple trace levels can be specified by adding the decimal/hexadecimal numbers (which equates to a binary OR), for example to turn on both EPM and TAR levels would be 2112 (decimal), or 0x840 (hexadecimal).  Mulitple trace levels can also be defined by specifying multiple mnemonics in a comma separated list, for example for both EPM and TAR tracing the mnemonic debug level would be "EPM,TAR".
    The default debug level is None (OFF).
**STATISTICS_TIMEOUT** (Optional)

    Specifies how frequently the RGP and its associated child processes log their statistics in the TRE Monitor while the trergp is active.  This value is the number of seconds between each successive call to STATISTICS_FUNCTION while the RGP is running.   STATISTICS_FUNCTION is also called on commencement and completion of each new Tuxedo request.  If not specified, statistics are not generated.
**STATISTICS_FUNCTION` `**(Optional)

    Specifies the function that is called every STATISTICS_TIMEOUT seconds while the RGP is processing. This function should contain a call to function RGPStats?{}().  The default STATISTICS_FUNCTION is RGPLogStatistics&().
**PRORATE_MONTH_LENGTH** (Optional)

    Determines what value to use as the number of days per month when calculating the duration of an active period.  If set to 'Days in start month' the RGP will use the actual number of days per month. Otherwise the RGP will use the 'Days Per Month' value from the 'Recurring' tab of the tariff definition.  If set to 'Average days in month' and the average days per month is not specified on the tariff, the actual days per month will be used instead.  The default value is 'Days in start month'. See Calculating Durations for more details. 
**GLOBAL_DA_CACHE_SIZE` `**(Optional)

    The size of the cache of derived attributes with a storage context of global. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" eg. 100M then the cache's size is the number of mega bytes that the cache is able to consume.
**NON_GLOBAL_DA_CACHE_SIZE` `**(Optional)

    The size of the cache of derived attributes with a storage context of service or customer node. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" eg. 100M then the cache's size is the number of megabytes that the cache is able to consume.
**RENTAL_END_BEFORE_BILL_DATE** (Mandatory)

    Determines the formula used for calculating the desired end date of rental periods. If set to FALSE and the effective date has a time componnent of 23:59:59 then: 

`DesiredEndDate = EffectiveDate + RecurringPeriod + AdvancePeriod `

    Otherwise:

`DesiredEndDate = trunc(EffectiveDate) - 1 second + RecurringPeriod +
AdvancePeriod`

    See Calculating the charge period for more details.  This setting should match USAGE_CHARGES_BEFORE_BILL_DATE in the BGP.  The default value is FALSE.
**ROUND_ENTITY_HISTORY** (Optional)

    Determines the RGP's behaviour when dealing with period start and end dates of entity history records (product instances, services, equipment items and facility group instances) that don't align with the beginning or end of a day respectively. See Determining active periods for more information. This value may also be date ranged via the RgpConfiguration?{} function as described below.
    

  * If set to 'None', the RGP performs no rounding on entity period start and period end dates.  
  * If set to 'Full Day', period start dates are rounded back to 00:00:00 time on the same day. Period end dates will be rounded forward to 23:59:59 time on the same day. 
  * If set to 'Nearest Day', period start dates prior to 12:00:00 midday will be rounded back to 00:00:00 time on the same day; period start dates 12:00:00 midday and after will be rounded forward to the following day with 00:00:00 time. Period end dates prior to 12:00:00 midday will be rounded back to the previous day with 23:59:59 time; period end dates 12:00:00 midday and after will be rounded forward to 23:59:59 time on the same day. 

NOTE: If period start date is at 12:00:00 midday, the period start date will
be forwarded to 00:00:00 time on the next day and period end date will be
rounded to 23:59:59 on the same day.

**PRORATE_ADVANCE_PERIOD** (Optional)

    (5.01.20) If this attribute is set to 1 (True), then the RGP will apply pro-rating to calculate the end date of the charge period even if the difference between the desired end bill date and the charge period start date is less than one rental period and the charge period start date is greater than the bill run effective date. By default the RGP does not apply pro-rating under these conditions. Refer to Calculating the Charge Period for further details.  The value of this attribute defaults to False.
**FILE_TIMEOUT** (Optional)

    This attribute specifies the maximum period of time the RGP will wait for the final event file to be processed by the ENM, that is, this value is passed in the Timeout& parameter in the final call to biEnmFileProcessByName&.The value is in seconds and defaults to four hours. 

If any of the above attributes marked as mandatory are not present, the RGP
server will fail to boot.

Multiple RGP servers may use the same RGP configuration.

Because the RGP adjusts previously generated events, changes to the
configuration may result in adjustments to events that were generated using an
earlier configuration. To aid migration to a modified configuration, the
BASE_INSTALL function RgpConfiguration?{} is called at startup to obtain date-
ranged values for certain configuration attributes. This function takes the
RGP configuration sequence Id and returns a hash of configuration attribute
names to a two dimensional array indicating the end dates and respective
values for the attribute.

For example:

`  var lCfgOverride?{'ROUND_ENTITY_HISTORY'}[] :=  
     [[ to_date('20/05/2005', 'DD/MM/YYYY'), ReferenceCodeByLabel&('RGP_ROUND_ENTITY_HISTORY', 'NONE') ],   
      [ to_date('01/06/2006', 'DD/MM/YYYY'), ReferenceCodeByLabel&('RGP_ROUND_ENTITY_HISTORY', 'NEAREST_DAY') ]];  
  return lCfgOverride?{};`

For the example above, the following would apply:

**Effective Start Date (inclusive)** |  **Effective End Date (inclusive)** |  **ROUND_ENTITY_HISTORY Value**  
---|---|---  
`SUNRISE` | 20/05/2005 00:00:00 | 'None'  
20/05/2005 00:00:01 | 01/06/2006 00:00:00 | 'Nearest Day'  
01/06/2006 00:00:01 | `SUNSET` | ROUND_ENTITY_HISTORY value from configuration item.  
  
Only the 'ROUND_ENTITY_HISTORY' configuration attribute is currently supported
by this functionality. By default this function returns an empty hash and no
date ranging of configuration values is performed.

The values returned from this function override the configuration item for the
respective range of start and end dates of entities and events. For start and
end dates later than the maximum returned end date, the value from the
configuration item is used. To prevent adjustments of existing events, the
configured end date for the previous configuration should be set to the
maximum period end date of existing events plus one day to accommodate
rounding, i.e:` "SELECT MAX(period_end_date) + 1 FROM rgp_normalised_event".`

In addition to configuration attributes, the process must know the correct
format for event records written to output files. This will differ between
installations, so details are stored in the database in the DIRECT_VARIABLE_V
view. This table contains a list of column names used for event records and
their ordering. The RGP retrieves this information directly from the table.
The RGP produces only some of the columns (other mandatory columns are filled
in by the event normalisation process), however, the records output by the RGP
have the correct number of attributes in the correct order. Those attributes
not generated by the RGP are set to NULL.

[Contents]

* * *

## Services

  * **biRental**  

Contains all of the functions to generate rentals. The functions currently
implemented for this service are:

    * biRentalGenerate&

  * **biQuoteRental**  

This service is advertised in a dedicated RGP server process used for quoting
purposes. This service performs rental generation processes for generating
quotes. The functions currently implemented for this service are:

    * biQuoteRentalGenerate&

[Contents]

* * *

## Tuxedo Server Functions

The following functions are handled by the RGP:

biRentalGenerate& | biRentalGenerate& (Interim mode)  
---|---  
biRentalGenerate& (Arrears Only mode) | biQuoteRentalGenerate&  
biRentalGenerate& (Rental Offset) |   
  
### Function biRentalGenerate&

**Declaration**

    
    
    biRentalGenerate&(BillRunId&,
                      EffectiveDate~,
                      BillRunOperationId&,
                      EffectiveDayOfMonth&
                      AdjustmentInd&,
                      QAInd&,
                      RootCustomerNodeList&[],
                      var SuccessCustomerNodeList&[],
                      var ErrorCustomerNodeList&[],
                      var Statistics?{})
    
    
    **biRentalGenerateCorporate &(BillRunId&,
    			   EffectiveDate~, 
    			   BillRunOperationId&,
    			   EffectiveDayOfMonth&, 
    			   AdjustmentInd&, 
    			   QAInd&,
    			   RootCustomerNodeList&[], 
    			   var SuccessCustomerNodeList&[],
    			   var ErrorCustomerNodeList&[],
    			   var OperationStatistics?{})
    ******
    
    
    **Parameters**

BillRunId& | The id of the bill run being processed. This can be ascertained by querying the  BILL_RUN_OPERATION table, but is passed for convenience. If AdjustmentInd&=TRUE, this may refer to the id of an existing unbilled bill run.  
---|---  
EffectiveDate~ | Effective date of the bill run  
BillRunOperationId& | The unique id of this particular (RGP/RAP) operation. Used to populate the CUSTOMER_NODE_BILL_RUN table. Note: a given run of the BillRunId& may have multiple BillRunOperationId&s.  
EffectiveDayOfMonth& | The target day of the month events were to be generated for.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter due to months not having enough days in them. See The EFFECTIVE_DAY_OF_MONTH field in BILL_RUN for more details.  
AdjustmentInd& | Indicates whether the server must generate rentals or adjustments. TRUE indicates adjustment mode (current RAP mode behaviour), FALSE indicates rental mode (current Rental mode behaviour).  
QAInd& | Indicates if the server should operate in temporary or QA mode. TRUE indicates a temporary bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | The list of root customer nodes for which rentals or adjustments must be calculated. The list will contain a single entry in the case of an on-demand bill run. The list may not contain duplicate Ids and each Id must represent a root customer node.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server either due to the customer's error threshold being exceeded or due to a fatal error  
var Statistics?{} | EventCount, ErrorEventCount, NumRgpFilesGenerated, RatedEventCount and CorruptEventCount. If NumRgpFilesGenerated = 0 then no stats are returned.  
      
    
    **Returns**

Returns TRUE on success, raises an error otherwise.

    
    
    **Description** 

The RGP server receives a list of root customer nodes to (re) generate events
for.   From this list the server generates a list of all of the customer nodes
to process and then process them in the root node order received and in the
mode specified.

Modes:

**Mode** | **Parameter** | **Description**  
---|---|---  
Recurring Mode | AdjustmentInd& = FALSE | Generate recurring events  
Adjustment Mode | AdjustmentInd& = TRUE | Generate retrospective adjustments  
Real Mode | QAInd& = FALSE | Generate real, permanent events  
QA Mode | QAInd& = TRUE | Generate temporary QA events  
  
No events generated in QA mode will be used to bill the customer.  For a QA
mode run to be made real, revoke the QA bill run and re-run it with the QA
mode turned off.

biRentalGenerateCorporate&() is a wrapper around  RentalGenerate&() which can
be used for Corporate Customers. Only difference is in the remote service
name, biRentalCorp being used in biRentalGenerateCorporate&(). This to  allow
Corporate customers to be directed to their own own set of rgp servers  which
may have a different configuration more suited to the processing of large
Corporate hierarchies.

    
    
    **Implementation** 

The biRentalGenerate& function is implemented with the RentalGenerateFunc
class, which  inherits from the TreSvcFunc class.  The main processing takes
place in RentalGenerateFunc::Execute(), which creates an rgp generation
controller based on whether or not the server has been booted in single or
multiprocess mode. In single process mode the controller is an
RgpGenerationController object.  The multi process mode is implemented using
an RgpGenerationContProxy, which interacts with the ProcessProtocol to send
messages to the child processes and retrieves values from the child processes.

Once the generator is created, the RgpServerController::Generate() is called,
which interacts with the rgp generation controller to:

  1. Lock the root customer nodes via the NodeManager, then commit the customer node locks to the database.
  2. Retrieves all tariffs for each of the customer nodes
  3. Sends each tariff to the rgp generation controller to process (create RGP_NORMALISED_EVENT rows and output the rgp event file)
  4. Retrieves the result status of each tariff that was sent (success or failure)
  5. Update the finish status for each root customer node using the NodeManager.
  6. Composes the return arrays of successful or failed customer nodes.

For the implementation of the recurring and adjustment event generation see
Section 2 - Rental Generation and Adjustment Processing. For information
specific to the RGP server, see below.

**Customer Hierarchy Locking  
**At the start of processing. the RGP attempts to lock all root customer nodes
in RootCustomerNodeList&[].  The root CUSTOMER_NODE record is updated with the
BillRunOperationId& and the process id of the RGP process performing the event
generation.  NB The lock will only update the root customer node record
successfully if the BillRunOperationId& is NULL.

Any hierarchies that are unable to be locked are considered to be in error and
are reported as such.

On completion of the RGP, all records are unlocked by clearing the
BILL_RUN_OPERATION_ID field in the CUSTOMER_NODE table.  If the severity of an
error is such that the server terminates abnormally while locks are in place,
it is the controller's responsibility to release the root customer node locks.
Under normal circumstances the locks made by the bill run operation will be
released, however a failure of the unlock may also mean that the external
system needs to manually unlock the records.

**Customer Node Bill Run Table**  
For each call the RGP server populates the CUSTOMER_NODE_BILL_RUN table with
all of the root customer nodes passed in RootCustomerNodeList&[]. The status
for each root customer node will initially be "Running".  As processing each
root customer node completes, the CUSTOMER_NODE_BILL_RUN table is updated with
the "Success" or "Fail" status as necessary. If "Fail", then an appropriate
error message is supplied.

**Error Handling**

There are several different classes of errors or exceptions that can take
place in the generation of rental events:

**Error Type** | **Description** | **Counts for hierarchy abort** | **Abort Heirachy** | **Counts for call abort** | **Aborts hierarchy and call**  
---|---|---|---|---|---  
Expression Error | An EPM expression failed | Yes | No | Yes | No  
Missing Data Error | Invalid data state - Usually a DVP error | Yes. | Yes | Yes | No  
Rating Error | An event was erred during rating | Yes | No | Yes | No  
Locking Error | Unable to obtain lock for hierarchy | No | Yes | Yes | No  
Rating Instance Error | The ENM_PROCESS_LIST does not include an ENM configured for the instance that the current hierarchy belongs to | No | Yes | Yes | No  
SIGTERM | Server received a SIGTERM signal | N/A | No | N/A | Yes  
Fatal Error | Any other error | N/A | No | N/A | Yes  
  
The biRentalGenerate&() can be considered to have two distinct areas where
exceptions can occur:

  * the handling of customer nodes, 
  * and the generation of RGP normalised events based on tariffs associated with those customer nodes.

Any non-fatal exceptions thrown by the customer node handler will result in
the immediate aborting of that customer node, which involves recording the
error against the appropriate CUSTOMER_NODE_BILL_RUN row, and add the node id
to the returned ErrorCustomerNodeList&[].

Non-fatal exceptions in tariff processing, including individual rating errors,
will accumulate at the root customer node level. When this number exceeds the
HIERARCHY_ERROR_THRESHOLD further processing of the hierarchy is aborted and
the root customer node Id will be returned in the ErrorCustomerNodeList&[].

When the number of errors for a given call exceeds CALL_ERROR_THRESHOLD, the
RGP aborts processing and returns the appropriate error code.  Note that each
hierarchy error is also used in the assessment of whether the call error
threshold has been exceeded.  For example, if the hierarchy error threshold is
three and the call error threshold is five, and four expression errors occur
in the first customer node, that customer hierarchy is failed.  The call
continues and the next customer hierarchy has three expression errors.  Even
though the hierarchy threshold has not been exceeded yet, the call error
threshold has been exceeded, so the whole call is aborted.

Although strictly speaking it is not an error, when the server receives a
SIGTERM, the server processes it as a fatal error condition.  It is handled by
the server signalling all child processes to SIGTERM, which aborts whatever
processing they were performing.  Once all child processes have shut down, the
server signal handler will command the RgpNodeManager to fail all customer
nodes (recording a SIGTERM error message in each CUSTOMER_NODE_BILL_RUN row),
and then the signal handler will throw an exception, which will be the final
abort of the processing, which will fail the biRentalGenerate&() call with an
error message stating that a SIGTERM was received.  

Note that if a SIGTERM is received during an Oracle OCI function it may result
in the prevention of further Oracle OCI function executions, which means the
failing of all of the customer nodes may also throw an exception.  In this
case the error message returned will state that a SIGTERM has been received,
and the error was not written to the customer node bill run table.

[Tuxedo Server Functions] [Contents]

* * *

### biRentalGenerate& (Interim mode)

biRentalGenerate& is overridden to allow support for interim invoicing mode.
When generating interim invoices, biRentalGenerate& is called with an extra
parameter InterimInd& which is a boolean flag indicating whether or not the
RGP should operate in interim mode.

**Declaration**

    
    
    biRentalGenerate&(BillRunId&,
                      EffectiveDate~,
                      BillRunOperationId&,
                      EffectiveDayOfMonth&
                      AdjustmentInd&,
                      QAInd&,
                      InterimInd&,
                      RootCustomerNodeList&[],
                      var SuccessCustomerNodeList&[],
                      var ErrorCustomerNodeList&[],
                      var Statistics?{})****
    
    
    **biRentalGenerateCorporate &(BillRunId&,
    			   EffectiveDate~, 
    			   BillRunOperationId&,	
    			   EffectiveDayOfMonth&, 
    			   AdjustmentInd&, 
    			   QAInd&,
    			   InterimInd&,
    			   RootCustomerNodeList&[], 
    			   var SuccessCustomerNodeList&[],
    			   var ErrorCustomerNodeList&[],
    			   var OperationStatistics?{}) **
    
    
    **Parameters**

BillRunId& | The id of the bill run being processed. This can be ascertained by querying the  BILL_RUN_OPERATION table, but is passed for convenience.  
---|---  
EffectiveDate~ | Effective date of the bill run  
BillRunOperationId& | The unique id of this particular (RGP/RAP) operation. Used to populate the CUSTOMER_NODE_BILL_RUN table. Note: a given run of the BillRunId& may have multiple BillRunOperationId&s.  
EffectiveDayOfMonth& | The target day of the month events were to be generated for.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter due to months not having enough days in them. See The EFFECTIVE_DAY_OF_MONTH field in BILL_RUN for more details.  
AdjustmentInd& | Indicates whether the server must generate rentals or adjustments. TRUE indicates adjustment mode (current RAP mode behaviour), FALSE indicated rental mode (current Rental mode behaviour).  
QAInd& | Indicates if the server should operate in temporary or QA mode. TRUE indicates a temporary bill run. FALSE indicates a real bill run  
InterimInd& | Indicates whether or not the server should operate in interim mode. In interim mode, only interim tariffs are considered for processing  
RootCustomerNodeList&[] | The list of root customer nodes for which rentals or adjustments must be calculated. The list will contain a single entry in the case of an on-demand bill run. The list may not contain duplicate Ids and each Id must represent a root customer node.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server either due to the customer's error threshold being exceeded or due to a fatal error  
var Statistics?{} | EventCount, ErrorEventCount, NumRgpFilesGenerated, RatedEventCount and CorruptEventCount. If NumRgpFilesGenerated = 0 then no stats are returned.  
      
    
    **Returns**

Returns TRUE on success, raises an error otherwise.

    
    
    **Description** 

The RGP server receives a list of root customer nodes to generate events for.
From this list the server generates a list of all of the customer nodes to
process and then process them in the root node order received and in the mode
specified.  If called with the InterimInd& flag set, the RGP will operate in
interim mode for the duration the the call.

**biRentalGenerateCorporate & (Interim Mode) is a wrapper  around
RentalGenerate(Interim Mode) which can be used for Corporate Customers.**

    
    
    **Implementation**

The implementation of this function is almost identical to biRentalGenerate&
except that the RGP operates in interim mode.

[Tuxedo Server Functions] [Contents]

* * *

### Function biRentalGenerate& (Arrears Only mode)

biRentalGenerate& is overridden to allow support for arrears only mode. Extra
parameters MaxPeriodStartDate~ and CurrentBillRunOnlyInd& are supplied, which
indicates the RGP/RAP should operate in arrears only rental generation and
adjustment mode.

**Declaration**

    
    
    biRentalGenerate&(BillRunId&,
                      EffectiveDate~,
                      BillRunOperationId&,
                      EffectiveDayOfMonth&
                      AdjustmentInd&, 
                      CurrentBillRunOnlyInd&,
    		  MaxPeriodStartDate~,
                      RootCustomerNodeList&[],
                      var SuccessCustomerNodeList&[],
                      var ErrorCustomerNodeList&[],
                      var Statistics?{})****
    
    
    **Parameters**

BillRunId& | The id of the bill run being processed. This can be ascertained by querying the  BILL_RUN_OPERATION table, but is passed for convenience. It may be the id of an existing unbilled bill run.  
---|---  
EffectiveDate~ | Effective date of the bill run  
BillRunOperationId& | The unique id of this particular RGP operation. Used to populate the CUSTOMER_NODE_BILL_RUN table. Note: a given run of the BillRunId& may have multiple BillRunOperationId&s.  
EffectiveDayOfMonth& | The target day of the month events were to be generated for.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter due to months not having enough days in them. See The EFFECTIVE_DAY_OF_MONTH field in BILL_RUN for more details.  
AdjustmentInd& | Indicates whether the server must generate rentals or adjustments. TRUE indicates adjustment mode (current RAP mode behaviour), FALSE indicated rental mode (current Rental mode behaviour).  
CurrentBillRunOnlyInd& | Indicates whether the rental adjustment should be applied to the current bill run only (BillRunId&) or all previous bill runs. TRUE indicates the current bill run only, FALSE indicates all previous bill runs (normal RAP behaviour). Typically this indicator would be set when running multiple advance bill runs to prevent the generation of adjustment events against earlier advance bill runs that have not yet been billed. Only applies when AdjustmentInd& is set to TRUE.   
MaxPeriodStartDate~ | The value specifies the maximum period start date for rental event generation. The RGP will not consider generating events for entity/tariffs that have a period start date greater or equal to this date. This is used to prevent generating rental events for rental periods that begin beyond a specified date, usually this is set to the effective date of the bill run for arrears generation. If set to an undefined value the RGP ignores the setting and generates all required events. Only applies when AdjustmentInd& is set to FALSE.  
RootCustomerNodeList&[] | The list of root customer nodes for which rentals or adjustments must be calculated. The list will contain a single entry in the case of an on-demand bill run. The list may not contain duplicate Ids and each Id must represent a root customer node.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server either due to the customer's error threshold being exceeded or due to a fatal error  
var Statistics?{} | EventCount, ErrorEventCount, NumRgpFilesGenerated, RatedEventCount and CorruptEventCount.If AdjustmentInd&=TRUE, further statistics from biRgpFileCreate& and zbiEventRevoke& are populated: 

  * RgpEventsDeleted - The total number of entries deleted from RGP_NORMALISED_EVENT.
  * Events - Total number of normalised events deleted.
  * Charges - Total number of CHARGE records deleted.
  * Services - Total number of distinct services that were updated.
  * Accounts - Total number of distinct accounts that were updated.
  * Subtotals - Total number of SUBTOTAL_RATING_VALUE records that were updated.
  * Guidance - The number of distinct GL Guidance aggregate records that were updated as a result of deleting these events

  
      
    
    **Returns**

Returns TRUE on success, raises an error otherwise.

    
    
    **Description** 

The RGP server receives a list of root customer nodes to generate events for.
From this list the server generates a list of all of the customer nodes to
process and then process them in the root node order received and in the mode
specified. Arrears only mode is intended to be run as a future bill run with
an effective date ahead of the bill run period last invoiced. This is done as
a means of populating the CHARGE table with arrears rental charges for a
billing period that would otherwise only be inserted retrospectively.

    
    
    **Implementation**

The implementation of this function is almost identical to biRentalGenerate&
except the rental generation only generates events for entity/tariffs that
have a period start date less than MaxPeriodStartDate~. The period end dates
for the events may end after this date however.

For the current bill run, the RAP will revoke and regenerate events that
require adjusting, rather than generate adjustment events. If multiple
unbilled bill runs are being run in advance, the RAP can be restricted to
operating on the current bill run only with the CurrentBillRunOnlyInd& flag.
This prevents the RAP from generating an adjustment event against an earlier
unbilled bill run. Such events should be revoked and regenerated by the
earlier bill run itself.

[Tuxedo Server Functions] [Contents]

* * *

### Function biQuoteRentalGenerate&

**Declaration**

    
    
    biQuoteRentalGenerate&(BillRunId&,
                      EffectiveDate~,
                      BillRunOperationId&,
                      EffectiveDayOfMonth&
                      AdjustmentInd&,
                      QAInd&,
                      RootCustomerNodeList&[],
                      var SuccessCustomerNodeList&[],
                      var ErrorCustomerNodeList&[],
                      var Statistics?{})

**Parameters**

BillRunId& | The id of the bill run being processed. This can be ascertained by querying the  BILL_RUN_OPERATION table, but is passed for convenience. If AdjustmentInd&=TRUE, this may refer to the id of an existing unbilled bill run.  
---|---  
EffectiveDate~ | Effective date of the bill run  
BillRunOperationId& | The unique id of this particular (RGP/RAP) operation. Used to populate the CUSTOMER_NODE_BILL_RUN table. Note: a given run of the BillRunId& may have multiple BillRunOperationId&s.  
EffectiveDayOfMonth& | The target day of the month events were to be generated for.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter due to months not having enough days in them. See The EFFECTIVE_DAY_OF_MONTH field in BILL_RUN for more details.  
AdjustmentInd& | Indicates whether the server must generate rentals or adjustments. TRUE indicates adjustment mode (current RAP mode behaviour), FALSE indicates rental mode (current Rental mode behaviour).  
QAInd& | Indicates if the server should operate in temporary or QA mode. TRUE indicates a temporary bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | The list of root customer nodes for which rentals or adjustments must be calculated. The list will contain a single entry in the case of an on-demand bill run. The list may not contain duplicate Ids and each Id must represent a root customer node.  
var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server either due to the customer's error threshold being exceeded or due to a fatal error  
var Statistics?{} | EventCount, ErrorEventCount, NumRgpFilesGenerated, RatedEventCount and CorruptEventCount. If NumRgpFilesGenerated = 0 then no stats are returned.  
  
**Returns**

Returns TRUE on success, raises an error otherwise.

**Description**

The RGP server receives a list of root customer nodes to (re) generate events
for.   From this list the server generates a list of all of the customer nodes
to process and then process them in the root node order received and in the
mode specified.

Modes:

**Mode** | **Parameter** | **Description**  
---|---|---  
QA Mode | QAInd& = TRUE | Generate temporary QA events  
  
The intent of this function is that it is only used for generating quotes.

No events generated in QA mode will be used to bill the customer.  For a QA
mode run to be made real, revoke the QA bill run and re-run it with the QA
mode turned off.

**Implementation**

The implementation of this function is identical to biRentalGenerate&.

[Tuxedo Server Functions] [Contents]

* * *

### Function biRentalGenerate&

biRentalGenerate& is overridden to allow support for separating rental date
from effective date. When generating rentals, biRentalGenerate& is called with
an extra parameter RentalEffectiveDate~ which specifies the rental effective
date RGP should use for calculating rental charge period.

**Declaration**

    
    
    biRentalGenerate&(BillRunId&,
                      EffectiveDate~,
                      RentalEffectiveDate~,
                      BillRunOperationId&,
                      EffectiveDayOfMonth&
                      AdjustmentInd&,
                      QAInd&,
                      RootCustomerNodeList&[],
                      var SuccessCustomerNodeList&[],
                      var ErrorCustomerNodeList&[],
                      var Statistics?{})
    
    
    **biRentalGenerateCorporate &(BillRunId&,
                               EffectiveDate~,
                               RentalEffectiveDate~,
                               BillRunOperationId&,
                               EffectiveDayOfMonth&,
                               AdjustmentInd&,
                               QAInd&,
                               RootCustomerNodeList&[],
                               var SuccessCustomerNodeList&[],
                               var ErrorCustomerNodeList&[],
                               var OperationStatistics?{})
    ******
    
    
    **Parameters**

BillRunId& | The ID of the bill run being processed. This can be ascertained by querying the  BILL_RUN_OPERATION table, but is passed for convenience. If AdjustmentInd&=TRUE, this may refer to the ID of an existing unbilled bill run.  
---|---  
EffectiveDate~ | Effective date of the bill run  
RentalEffectiveDate~ | Date-time for rental charge period calculations.  In the variants of this interface without this parameter, the EffectiveDate~ parameter is used to as the Date-time for rental charge period calculations. The variant of this interface with this parameter allows a different date from the bill run Effective Date to be used for rental charge period calculations. This provides a way for bill runs to be performed that have their rentals offset from the usage that is billed.   
BillRunOperationId& | The unique id of this particular (RGP/RAP) operation. Used to populate the CUSTOMER_NODE_BILL_RUN table. Note: a given run of the BillRunId& may have multiple BillRunOperationId&s.  
EffectiveDayOfMonth& | The target day of the month events were to be generated for.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter due to months not having enough days in them. See The EFFECTIVE_DAY_OF_MONTH field in BILL_RUN for more details.  
AdjustmentInd& | Indicates whether the server must generate rentals or adjustments. TRUE indicates adjustment mode (current RAP mode behaviour), FALSE indicates rental mode (current Rental mode behaviour).  
QAInd& | Indicates if the server should operate in temporary or QA mode. TRUE indicates a temporary bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | The list of root customer nodes for which rentals or adjustments must be calculated. The list will contain a single entry in the case of an on-demand bill run. The list may not contain duplicate Ids and each Id must represent a root customer node. | var SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
var ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed by the server either due to the customer's error threshold being exceeded or due to a fatal error  
var Statistics?{} | EventCount, ErrorEventCount, NumRgpFilesGenerated, RatedEventCount and CorruptEventCount. If NumRgpFilesGenerated = 0 then no stats are returned.  
      
    
    **Returns**

Returns TRUE on success, raises an error otherwise.

    
    
    **Description** 

The RGP server receives a list of root customer nodes to (re) generate events
for.   From this list the server generates a list of all of the customer nodes
to process and then process them in the root node order received and in the
mode specified.

**Implementation**

The implementation of this function is identical to biRentalGenerate&, except
the rental charges are generated using Rental Effective date. The period end
date for the events are calculated using RentalEffectiveDate.

[Tuxedo Server Functions] [Contents]

* * *

### Function biRentalRevoke&

**Declaration**

    
    
    biRentalRevoke&(BillRunId&,
                    EffectiveDate~,
                    BillRunOperationId&,
                    **const** RootCustomerNodeList&[],
                    **var** SuccessCustomerNodeList&[],
                    **var** ErrorCustomerNodeList&[],
                    **var** Statistics?{})
    
    
    **Parameters**

BillRunId& | The id of the bill run being processed.   
---|---  
EffectiveDate~ | Effective date of the bill run  
BillRunOperationId& | The unique id of this particular (RGP/RAP) operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.   
**const**  
RootCustomerNodeList&[] | The list of root customer nodes for which rental or adjustment are to be revoked.   
**var** SuccessCustomerNodeList&[] | A list of all root customer ids that were successfully processed which is returned to the calling process.   
**var** ErrorCustomerNodeList&[] | A list of root customer ids that were not successfully processed.   
**var** Statistics?{} | Statistics about the events that were revoked.  The following keys are returned in the hash:

  * RgpEventsDeleted - The total number of entries deleted from RGP_NORMALISED_EVENT.
  * ErrorEventsDeleted - The total number of normalised event error records deleted.
  * ChargesDeleted - Total number of CHARGE records deleted.
  * EventsDeleted - Total number of normalised events deleted.
  * Subtotals - Total number of SUBTOTAL_RATING_VALUE records that were updated.
  * Accounts - Total number of distinct accounts that were updated.
  * Services - Total number of distinct services that were updated.

  
      
    
    **Returns**

Size of SuccessCustomerNodeList&[] on completion, aborts on failure.

**Description**

Revokes rental events and rental adjustment events for the customer node
hierarchies specified.  Any values that have been aggregated into rating
subtotals are also revoked.

**Implementation**

For each root customer node passed to the function.  The
CUSTOMER_NODE_BILL_RUN table is updated to indicate that the revoke process is
running.  The customer hierarchy is then locked.  Entries in
RGP_NORMALISED_EVENT for the specified BILL_RUN_ID and ROOT_CUSTOMER_NODE_ID
are deleted.  The number of normalised event and normalised event error
records that will be deleted from each file is retrieved and used to update
the NORMALISED_EVENT_FILE record.  The NORMALISED_EVENT_ERROR records are then
deleted.  The NORMALISED_EVENT table is queried using BILL_RUN_ID and
ROOT_CUSTOMER_NODE_ID to retrieve a list of NORMALISED_EVENT_ID's and
CHARGE_START_DATE's.  These details are then passed to the biEventRevoke
function, to do the revoking of charges and normalised events.  The
CUSTOMER_NODE_BILL_RUN entry is then updated to indicate the revoke operation
was successful and the hierarchy unlocked.  Changes are committed after 10
seconds have past, this check is made after processing each hierarchy.  If an
error is raised during revoking for the hierarchy, the customer node is added
to the list of erred customers.  If more than five customer hierarchies error
the process terminates.

[Tuxedo Server Functions] [Contents]

* * *

## EPM Built-in Functions

CurrencyPurge& | CustomerNodeDAPurge&  
---|---  
DerivedTablePurge& | FunctionPurge&  
ReferenceTypePurge& | ReferenceTypePurgeById&  
ReferenceTypePurgeByLabel& | ServiceDAPurge&  
SubtotalPurge& | TariffPurge&  
RentalBillFromDate~ | RentalBillToDate~  
RentalDuration# | RentalAdjustmentMode&  
RentalBillRunId& | RentalBillRunEffectiveDate~  
RentalEntityActiveDate~ | RentalEntityCancelledDate~  
RGPStats?{} | RentalSplit&  
InterimMode& | RGPTrace& |    
RentalArrearsMaxPeriodStartDate~ | LoggerReload& |    
RentalEffectiveDate~  
  
In addition to these functions, the RGP attaches to the CNM and SCM and hence
has access to the following EPM built-in functions.

CustomerNodeFetch?[]  | CustomerNodeInCache&  
---|---  
CustomerNodeTableContents?[] | CustomerNodeTableLookup&  
CustomerNodeTableLookup?[]  | CustomerNodePurge&  
  
Refer to the CNM module for more information on these functions.

ServiceFetchByName& | ServiceFetchById&  
---|---  
ServiceInCache& | ServiceTableLookup&()   
ServiceTableContents?[]()  |    
  
Refer to the SCM module for more information on these functions.

[Contents]

* * *

### Function CustomerNodeDAPurge&

**Declaration**

    
    
    CustomerNodeDAPurge&(CustomerNodeId&)

**Parameters**

CustomerNodeId& | The ID of a customer node for which DA information is being purged.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function causes the RGP to purge Derived Attribute information for the
specified customer node from its DatNonGlobalCache.

**Implementation**

This callback function is registered in the RGP Parser.
DatNonGlobalCache::PurgeEntity() is used to purge the DA information of the
specified customer node. Note that because the RGP connects to the CNM (and
therefore has access to the functions registered by the CNM) , this function
differs in name from the CNM callback function CustomerNodePurge. The names
differ to allow both callback functions to co-exist in the RGP parser.

[EPM Built-in Functions] [Contents]

* * *

### Function CurrencyPurge&

**Declaration**

    
    
    CurrencyPurge&(CurrencyId&)

**Parameters**

CurrenryId& | The ID of the currency to purge from the CCM.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges data (such as conversion rates) for the specified
currency from the RGP's Currency Cache Module (CCM). The CCM is a process
specific cache that caches data for currencies such as conversion rates.

**Implementation**

This callback function calls Ccm:GetInstance()->Purge() to remove the required
data.

[EPM Built-in Functions] [Contents]

* * *

### Function DerivedTablePurge&

**Declaration**

    
    
    DerivedTablePurge&(TableName$)

**Parameters**

TableName$ | Name of the Derived Attribute Table to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges Derived Attribute Table data from the RGP's caches.

**Implementation**

This callback function attempts to purge from the Derived Attribute Table
caches (both Global and non Global), using DamTableCacheGlobal
(DamTableCacheGlobal::GetInstance()->Purge()) and DamTableCacheNonGlobal
(DamTableCacheNonGlobal::GetInstance()->Purge()), since the type of the
specified DA Table is not known (each DA Table can only be in one of these
caches, not both).

[EPM Built-in Functions] [Contents]

* * *

### Function FunctionPurge&

**Declaration**

    
    
    FunctionPurge&(FunctionName$)

**Parameters**

FunctionName$ | The name of the function to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges the specified function from the RGP's parser.

**Implementation**

The RGP's parser is a BuiltInSQLFunctionParser, so the PurgeFunction method is
used to remove/reload the specified function from the parser.

[EPM Built-in Functions] [Contents]

* * *

### Function ReferenceTypePurge&

**Declaration**

    
    
    ReferenceTypePurge&(ReferenceTypeAbbreviation$)

**Parameters**

ReferenceTypeAbbreviation$ | The abbreviation of the Reference Type to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges the specificed reference type data from the RGP's
Reference Type Cache.

**Implementation**

The callback function uses ReferenceTypeCache::GetInstance()->PurgeByAbbrev()
to clear the data for the specified reference type. biReferenceTypePurge& is
handled in the RGP via this callback function instead of the normal callback
function registered by the BuiltInSQLFunctionPaser class because the RGP
requires some special handling to allow for RGP child processes.

[EPM Built-in Functions] [Contents]

* * *

### Function ReferenceTypePurgeById&

    
    
    ReferenceTypePurgeById&(ReferenceTypeId&)

**Parameters**

ReferenceTypeId& | The Id of the Reference Type to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges the specificed reference type data from the RGP's
Reference Type Cache.

**Implementation**

This function works in a similar fashion to ReferenceTypePurge&, above, but it
purges via Id (ReferenceTypeCache::GetInstance()->PurgeById()) instead of
abbreviation..

[EPM Built-in Functions] [Contents]

* * *

### Function ReferenceTypePurgeByLabel&

    
    
    ReferenceTypePurgeByLabel&(TypeLabel$)

**Parameters**

TypeLabel& | The label of the Reference Type to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function purges the specificed reference type data from the RGP's
Reference Type Cache.

**Implementation**

This function works in a similar fashion to ReferenceTypePurge&, above, but it
purges via Label (ReferenceTypeCache::GetInstance()->PurgeByLabel()) instead
of abbreviation..

[EPM Built-in Functions] [Contents]

* * *

### Function ServiceDAPurge&

**Declaration**

    
    
    SerivcePurge&(ServiceId&)

**Parameters**

ServiceId& | The ID of a service for which DA information is being purged.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This function causes the RGP to purge Derived Attribute information for the
specified service from its DatServiceProductCache and DatNonGlobalCache.

**Implementation**

DatServiceProductCache::PurgeService and DatNonGlobalCache::PurgeEntity() are
used to purge the DA and companion product instance information for the
specified service. ServiceDAPurge is normally handled in the
BuiltInSQLFunctionParser, but the existence of RGP child processes requires
some specialised handling, so the RGP registers its own version of
ServiceDAPurge.

[EPM Built-in Functions] [Contents]

* * *

### Function SubtotalPurge&

**Declaration**

    
    
    SubtotalPurge&(SubtotalId&)

**Parameters**

SubtotalId& | The Id of the subtotal to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This callback function purges subtotal data from the RGP's cache.

**Implementation**

The subtotal data is purged from the RGP's Subtotal cache using
Sub::GetInstance()->Delete().

[EPM Built-in Functions] [Contents]

* * *

### Function TariffPurge&

**Declaration**

    
    
    TariffPurge&(TariffId&)

**Parameters**

TarifflId& | The Id of the tariff to purge.  
---|---  
  
**Returns**

Returns TRUE. Errors are logged as appropriate.

**Description**

This callback function purges tariff data from the RGP's cache.

**Implementation**

The tariff data is purged using
RgpTariffDetailsCache::GetInstance()->Delete().

[EPM Built-in Functions] [Contents]

* * *

### Function RGPStats?{}

**Declaration**

    
    
    RGPStats?{}()

**Returns**

Returns a hash structure containing statistics that the RGP has gathered since
boot time

**Description**

The statistics returned in the hash structure depend on the configuration of
the RGP.   If the function is called from the parent process, the returned
hash contains the following statistics:

**Key** | **Description**  
---|---  
Events | (Integer) Number of events generated   
ProcessingTime | (Real) Number of seconds spent processing biRentalGenerate& requests, this includes time spent waiting for responses from children  
RequestsSent | (Integer) Requests sent to children   
ResponsesReceived | (Integer) Responses received from children   
WaitTime | (Real) Number of seconds spent waiting for responses from children   
ProcessName | (String) Name of RGP process, this will be trergp for the parent process  
  
Of course, RequestsSent, ResponsesReceived and WaitTime will all be zero if
the RGP is running in single process mode.  If called from the child process,
a hash containing the following statistics is returned:

**Key** | **Description**  
---|---  
Events | (Integer) Number of events generated   
ProcessingTime | (Real) Number of seconds spent processing requests from the parent process  
RequestsReceived | (Integer) Requests received from the parent process  
ProcessName | (String) Name of RGP process, this will be rgpchild for all child processes  
ParentProcessId | (Integer) Process identifier of this child's parent process  
  
**Implementation**

Singleton class RgpTreMonStats has a static member function GetInstance(),
this function is called to get a pointer to the RgpTreMonStats object for the
current process.  The appropriate accessor functions are called to gather the
required statistics into a hash structure.  This hash structure is returned.

[EPM Built-in Functions] [Contents]

* * *

### Function InterimMode&

**Declaration**

    
    
    InterimMode&()

**Description**

Determines if the RGP is running in interim mode.

**Returns**

1 (TRUE) if the RGP is running in interim mode, 0 (FALSE) otherwise

**Implementation**

RgpRunOptions::GetInstance() is called to get a pointer to the singleton
RgpRunOptions object. From this, RgpRunOptions::GetInterimMode() is called
which returns TRUE if the RGP is in interim mode, and FALSE otherwise.

[EPM Built-in Functions] [Contents]

* * *

### Function  RentalArrearsMaxPeriodStartDate~

**Declaration**

    
    
    RentalArrearsMaxPeriodStartDate~()

**Returns**

Returns the maximum period start date for event generation when operating in
arrears mode, or an undefined value if not operating in arrears only mode.

**Description**

Determines whether the RGP is running in arrears only mode and returns the
maximum period start date for event generation.

**Implementation**

RgpRunOptions::GetInstance() is called to get a pointer to the singleton
RgpRunOptions object. From this, RgpRunOptions::GetArrearsMaxPeriodStartDate()
is called which returns the MaxPeriodStartDate~ as specified in the
biRentalGenerate call. The value is undefined if this has not been specified
and the RGP is not operating in arrears only mode.

[Contents] [EPM Built-in Functions]

* * *

### Function LoggerReload&

**Declaration**

LoggerReload&()

**Parameters**

None.

**Description**

This function is overridden in order to propagate the logger reload to child
processes. Otherwise, it provides the same functionality as  LoggerReload&(1).

**Return Value**  
  
1 on success. Raises an error otherwise.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalBillFromDate~

**Declaration**

    
    
    RentalBillFromDate~()

**Returns**

Returns the start of the date range for which the RGP/RAP is looking at
generating rental events for the current entity and tariff.  Returns the date
of the activation or cancellation if called while processing a one-off tariff.
Returns an undefined value if called when the rgp is running in adjustment
mode.

**Description**

This function extracts the required information from the RGP, and determines
the date from which rental events are to be generated for the current charged
entity and tariff.  The value returned will be the maximum of

  1. The date on which the entity first became active. 
  2. 1 second after the the maximum end date for which rental events have been generated for this entity and tariff. 

Note that changes to tariff or entity statuses have no influence on the
calculation of this date.

**Implementation**

RgpParser::GetCurrentGenerator() is called to obtain a pointer to the current
RgpEventGenerator. This class acts as a hub of information about entities,
tariffs etc. RgpGenerator has a member function GetStart() which returns the
start date of the rental period of the current RGP/RAP run.

If the RGP/RAP is currently running in adjustment mode, an undefined value is
returned, otherwise the value returned by GetStart() is returned.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalBillToDate~

**Declaration**

    
    
    RentalBillToDate~()

**Returns**

Returns the inclusive end of the date range for which the rgp is looking at
generating rental events for the current entity and tariff.  Returns the date
of the activation or cancellation if called while processing a one-off tariff.
Returns an undefined value if called when the rgp is running in adjustment
mode.

**Description**

The date returned includes the effect of pro-rating. Note that changes to
tariff or entity statuses have no influence on the calculation of this date.

With a recurring charge period specified in months, problems can occur when
the day number of the starting month does not exist in the ending month, for
example, 31 January + 1 month = 30 February. In this situation, the end date
is rounded down to the last day of the target month and this is treated as a
full month.  The 'logical day of the month' that this event was bill up to
needs to be recorded in the generated event. The END_DAY_OF_MONTH column in
the RGP_NORMALISED_EVENT table is used to store this information.

**Implementation**

RgpParser::GetCurrentGenerator() is called to obtain a pointer to the current
RgpEventGenerator.  RgpEventGenerator has a member function GetEnd() which
returns the end date of the rental period of the current RGP/RAP run.

If the RGP/RAP is currently running in adjustment mode an undefined value is
returned, otherwise the date returned by GetEnd() is returned

[Contents] [EPM Built-in Functions]

* * *

### Function RentalDuration#

**Declaration**

    
    
    RentalDuration#()

**Returns**

This function returns the duration, with respect to the recurring period, of
the date range from RentalBillFromDate~() to RentalBillToDate~(). This
function returns an undefined value if called in adjustment mode.

**Description**

This function first determines the start and end dates that rental events must
be generated for the current charged entity and tariff combination.  It then
determines the duration between these two dates with respect to the recurring
charge period, taking into consideration end of month rental effects.

With a recurring charge period specified in months, problems can occur when
the day number of the starting month does not exist in the ending month, for
example, 31 January + 1 month = 30 February. In this situation, the end date
is rounded down to the last day of the target month and this is treated as a
full month.

**Implementation**

RgpParser::GetCurrentGenerator() is called to obtain a pointer to the current
RgpEventGenerator. The RgpEventGenerator's GetCalc() member function is called
to obtain a pointer to the RgpChargeTime object oPeriodCalculator. The
RgpChargeTime class has a member function called CalcDuration() which takes
two dates as arguments. The duration between these dates is returned in units
of the recurring charge period. RgpGenerator->GetStart() is passed as the
first argument and RgpGenerator->GetEnd() \+ 1 second is passed as the second
argument.

If the RGP/RAP is currently running in adjustment mode, an undefined value is
returned, otherwise the value returned by CalcDuration() is returned.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalAdjustmentMode&

**Declaration**

    
    
    RentalAdjustmentMode&()

**Returns**

This function returns information about the mode the RGP is running in.
Returns TRUE (1) if the RGP is running in adjustment mode, FALSE (0)
otherwise.

**Implementation**

Static function RgpRunOptions::GetInstance() is called to get a pointer to the
RgpRunOptions object.  RgpRunOptions::GetAdjustmentMode() is called to
determine whether or not the RGP is running in adjustment mode.  If
GetAdjustmentMode() returns true, 1 is returned, otherwise 0 is returned.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalBillRunId&

**Declaration**

    
    
    RentalBillRunId&()

**Returns**

This function returns the bill run associated with the current RGP/RAP run.

**Implementation**

Static function RgpRunOptions::GetInstance() is called to get a pointer to the
RgpRunOptions object.  RgpRunOptions::GetBillRunId() is called which returns
the id of the current bill run.  

[Contents] [EPM Built-in Functions]

* * *

### Function RentalBillRunEffectiveDate~

**Declaration**

    
    
    RentalBillRunEffectiveDate~()

**Returns**

Returns the effective date of the current bill run.

**Implementation**

Static function RgpRunOptions::GetInstance() is called to get a pointer to the
RgpRunOptions object.  RgpRunOptions::GetEffectiveDate() is called which
returns the effective date of the current bill run.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalEffectiveDate~

**Declaration**

**Returns**

Returns the rental effective date of the current bill run.

**Implementation**

Static function RgpRunOptions::GetInstance() is called to get a pointer to the
RgpRunOptions object.  RgpRunOptions::GetRentalEffectiveDate() is called which
returns the rental effective date of the current bill run.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalEntityActiveDate~

**Declaration**

    
    
    RentalEntityActiveDate~()

**Returns**

Returns the date and time at which the RGP/RAP considers that the entity first
became active. An undefined value is returned if this function is called while
processing a one off activation or cancellation tariff.

**Description**

This function determines the date that the current charged entity became
active. The process to do this depends on the type of charged entity ie
Product, Facility Group, Service or Equipment.  This specialisation is
accounted for in the RgpEntity class hierarchy.

**Implementation**

RgpParser::GetCurrentRgpGenerator() is called to obtain a pointer to the
current RgpEventGenerator object.  The RgpEventGenerator member function
GetEntity() returns a pointer to the current RgpEntity.
RgpEntity::FindActivation() is called which determines the date the entity
first became active.  Each charged entity class inherits from the base
RgpEntity.   The process for determining the activation date is defined in
these child classes.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalEntityCancelledDate~

**Declaration**

    
    
    RentalEntityCancelledDate~()

**Returns**

Returns the date at which the RGP/RAP considers that the entity became
cancelled. If the function is called in adjustment mode, or when processing a
one-off activation or cancellation tariff, an undefined value is returned.

**Description**

This function extracts the required information from the RGP and returns the
date and time the current charged entity became cancelled. If the charged
entity was not cancelled between RentalBillFromDate~() and
RentalBillToDate~(), an undefined value is returned

**Implementation**

RgpParser::GetCurrentGenerator() is called to obtain a pointer to the current
RgpEventGenerator object. From this, a pointer to the current charged entity
is obtained.   Each charged entity type has a static SQLCache object that
holds the history records associated with that charged entity.
RgpEntity->GetCancellation() is called to search through this SQLCache object
and find the first entry whose entity Id matches the current entity Id and
whose status is set to cancelled.

If the charged entity is a facility group, the procedure is slightly
different. On the tariff definition, the facility group can be set, or the
facility group can remain unset. To allow for these two situations, the
RgpFacilityGroupEntity class has two SQLCache objects. One is used if the
facility group is set, the other is used if the facility group is not set.
Therefore RgpFacilityGroupEntity is modified slightly to search the
appropriate SQLCache object depending on whether or not the facility group is
set.

If the RGP/RAP is currently running in adjustment mode, an undefined value is
returned, otherwise the value returned by FindCancellation() is returned.

[Contents] [EPM Built-in Functions]

* * *

### Function RGPTrace&

**

Declaration**

    
    
    RGPTrace&(DebugLevel$)

**

Parameters**  

DebugLevel$ | Diagnostic debug level.   
---|---  
  
**Returns**

Returns 1.

**Description**

This function sets the diagnostic debug level for this RGP to the level
specified by DebugLevel$. This value is interpreted in the same manner as the
`<debug level>` command-line argument.  


Setting a new trace level turns off any existing trace levels that may be
turned on, unless there is a "+" sign in front of the trace level.  A "+" sign
indicates that the trace level is additive (ie: don't turn off any existing
levels).   The following three examples turn on EVT and ORA level tracing:

ecp biTrcRental& ('+,EVT,ORA')  
ecp biTrcRental&('+,16,1')  
ecp biTrcRental&('17')

The first two examples above preserve the existing debug level, whereas the
last does not.

Debug information requests are propagated to the RGP child processes via the
IPC pipes and each child takes the same action as the parent upon receiving
the message.

**Implementation**

This function is implemented as a built-in function.  It is registered by the
RGP.

[Contents] [EPM Built-in Functions]

* * *

### Function RentalSplit&

**Declaration**

    
    
    RentalSplit&(const FieldNames$[], const FieldValues?[])

**Returns**

N/A

**Description**

This function is called from the assignment expression of a rental tariff and
causes the event currently being generated to be split in two.  Each event is
rated individually which gives this function the potential for making the RGP
sensitive to rate changes which involve updates to CB entities not directly
examined by the RGP.

The field names and values passed in via FieldNames$[] and FieldValues?[]
specify the values for the new event. FieldNames$[] is an array of field names
from the RGP_NORMALISED_EVENT table and FieldValues?[] is an array of the
corresponding field values.  As a minimum PERIOD_START_DATE must be specified.
If its value is less than the period start date of the current event, an error
is raised. If its value is equal to the period start date of the current
event, the event is not split and the function returns immediately.  If
PERIOD_END_DATE is specified, it must equal the period end date of the current
event, if not an error is raised.  If a field has a value assigned to it in
both RentalSplit& and an assignment expression, the value assigned in the
assignment expression will override that in RentalSplit&.

Note that if ROUND_ENTITY_HISTORY is set to TRUE and the specified
PERIOD_START_DATE does not have 00:00:00 time component, then it will be
rounded.

**Implementation**

When iterating through the timeline of periods considered active by the RGP,
each period has its eligibility and assignment expressions evaluated.  If a
call to RentalSplit& from an assignment expression causes the event to be
split, the current timeline period is split in two; ie. the current period is
shortened so that the period end date is 1 second less than the specified
period start date* for the new event, and a new timeline period is added after
the current with the specified period start date* and a period end equal to
that of the original event.  Any other fields that have values assigned to
them are stored so that they can be assigned to the following timeline period
prior to evaluating the eligibility and assignment expressions.  The new
timeline period is processed in the next iteration through the loop.  Note
that this new timeline period could further be split when its assignment
expressions are evaluated.

* Taking rounding into consideration if applicable (see ROUND_ENTITY_HISTORY)

[Contents] [EPM Built-in Functions]

* * *

### Function biTrcRental&

**Declaration**

    
    
    biTrcRental&(DebugLevel$)

**Parameters**

DebugLevel$ | The level of debug tracing required.  See the configuration item's debug level description for details on the levels.  
The level can be the integer representation of the level or the string
mnemonic representation.  
---|---  
  
**Description**

Sets the specified debug level for all the RGP servers running on the current
instance.

See the debug level description for the trace file naming convention.

**Implementation**

Calls the biTrcInvoke& function to invoke the RGPTrace& function with the
specified debug level within each trergp server on the current instance.

[Contents]

* * *

### Statistics

RGP Statistics are available from two places in CB. Firstly, function
biRentalGenerate&() creates a hash of statistics that is returned in parameter
'Statistics'.  These statistics are gathered over the whole
biRentalGenerate&() call and include the number of successful events generated
and the number of errored events generated.  The other place that statistics
are available is the TRE Monitor.   The former statistics are discussed
elsewhere in this document, therefore the remainder of this section only
discusses the statistics that are periodically logged in the TRE Monitor.

The statistics are gathered via the EPM call-back function RGPStats?{}().  The
statistics that this function returns depend on where it is called.  If the
function is called in the parent process, the appropriate statistics are
returned (See function RGPStats?{}()).  Different statistics are returned if
the function is called in the child process.  Once the statistics have been
gathered a call to biTREServerMonitor&() logs the statistics in the TRE
Monitor.

Configuration attributes determine how and how often the statistics are logged
in the TRE Monitor.  The configuration attribute STATISTICS_TIMEOUT determines
how often statistics are logged.  The RGP keeps a record of when statistics
were last logged.   In the main loop of the RGP, if STATISTICS_TIMEOUT seconds
have passed since the RGP last logged statistics, a function is called to log
the current statistics in the TRE Monitor.  If the RGP is running is multi
process mode, it also sends a message to each of its child processes telling
them to call the same function to log their statistics.

The actual function that is called in the main loop of the RGP, and by the
child processes, is determined by the STATISTICS_FUNCTION configuration
attribute.  This function is configurable and defaults to RGPLogStatistics&().

[Contents]

* * *

## Section 2 - Rental Generation and Adjustment Processing

The rental generation process server (RGP) produces events for the rating
engine to calculate recurring and one-off charges for customers for tariffs
where the real-time indicator column is not set (i.e.
TARIFF_RECURRING.REAL_TIME_IND_CODE is NULL). These events identify a service,
customer, product, and a tariff, and optionally a  facility group or
equipment. For recurring charges, the events also identify the period over
which the tariff applies, and the proportion of the normal tariff period
during which the product was active for the customer. Other fields can be
assigned by defining an assignment expression list for the recurring tariff.

Three aspects for event generation are expression driven. Each tariff may
include an expression list associated with eligibility, assignment, and
adjustment. If any expression in the eligibility list returns false (0) then
an event is _not_ generated. If any expression in the adjustment list returns
false (0) then an adjustment _is_ generated. The assignment list is used to
calculate field values for the normalised event. The effective date used for
evaluating all expressions in the RGP is the same as the date as of which the
event will be rated ie. the date assigned to SWITCH_START_DATE in the
RGP_NORMALISED_EVENT table. See "Outputting Events" for more information
regarding this.

Generation of these events is carried out by the RGP server on lists of root
customer nodes. Each root customer node is processed in the specified order
and for the specified effective date. In processing a root customer node, the
RGP retrieves a list of all of the nodes for the customer hierarchy and then
processes each customer node (not just root) in the hierarchy.

The configuration is loaded when the server initialises and the server must be
restarted in order for configuration changes to take effect.

Events are written to files with a configurable maximum number of events per
file. While the events for a given file are being generated, the file itself
is virtual, existing only as a record in the RGP_FILE table. The batch is
ready to be processed generally when the maximum number of events to generate
is reached. The RGP calls biRgpFileCreate& to create a physical file
containing the appropriate events from the RGP_NORMALISED_EVENT table,
specifying the file name and ID. When running against an existing bill run
operation in RAP mode, this call also specifies a hash of existing RGP_FILE
IDs and an associated array of file record numbers (RGP_FILE_RECORD_NR) from
the RGP_NORMALISED_EVENT table of events and charges to revoke before file
creation. The RGP then calls biEnmFileProcessByName& specifying the filename
and the event normalisation process to receive the file. This normalisation
process must be correctly configured to receive the event types generated by
the RGP, noting that recurring tariffs define their event type. In a multi-
instance environment, the RGP calls the appropriate instance specific versions
of these functions, to ensure that the event file is created and rated on the
correct instance.

Tariffs have a version field which is used to determine if event regeneration
is required. The version field is manually set, for example, when the charged
entity parameters that effect tariff calculations have been altered.

The RGP server calculates retrospective adjustments for recurring charges if
called in adjustment mode. Retrospective adjustments calculate appropriate
debits or credits for customers if active periods have been altered during the
billing period, or any of the adjustment list expressions return false. To
allow retrospective adjustments and other checks to be performed, the details
of each generated event are stored in the database in the RGP_NORMALISED_EVENT

[Contents]

* * *

## Database Integrity

A number of measures are taken by the RGP to ensure that the database is
maintained consistently. These include:

  * Each time a file is completed, updates to the database are committed. 
  * If the process is interrupted or fails, any uncommitted updates are rolled back. 

[Contents]

* * *

## Retrieving Product/Tariff Details

The product instances for which recurring or one-off charge events should be
generated by the server are retrieved from the database for each customer for
each root customer node passed to biRentalGenerate&. The relationship between
customer nodes, product instances, other charged entities, and events is
illustrated in the following figure:

**Figure 1: Relationships between entities**

Each customer can have a number of product instances. Each product instance
must have at least one service (and may have more), and may optionally have
facility group instances and associated equipment. Recurring and one-off
charge events for products and their associated charged entities are
potentially generated on each billing cycle.

Each product instance will normally be associated with at least two tariffs:
one for usage-based call charges, and another for recurring (rental) charges
which are usually paid in advance. The RGP generates rental events using the
recurring tariff associated with the product instance. More complex product
instances with additional recurring tariffs can exist, however, and the RGP
also generates events for these if they exist.

Each recurring or one-off tariff is associated with a particular charged
entity. The charged entity is either a product, facility group, service, or
equipment tariff. Product tariffs are applied only to product instances.
Facility group tariffs are applied only to the facility group instances
associated with a product instance. Facility group tariffs can optionally
identify a specific facility group to which they are applied. Service tariffs
are applied only to the services associated with a product instance. Equipment
tariffs are applied only to the equipment associated with the product
instance.

One-off charges are implemented through specific tariffs associated with a
product. The RGP applies these tariffs exactly once when certain events
associated with product lifecycle occur. Activation, and Cancellation of a
product instance, facility group instance, service or equipment item can
result in one-off charges (see the section on one-off charges). When multiple
events occur in one billing cycle, multiple one-off charges are generated.

All charge events must be associated with a service in the rating engine. The
C_PARTY_INTERNAL_ID is used to uniquely identify the service. It is set to the
unique internal identifier of the service associated with this rental event.

The set of product/tariff combinations that require rental charge events for a
particular run of the RGP is retrieved from the database by selecting from a
database join of the tables containing customer, product instance, and tariff
details. Since customers,  products and tariffs are date-ranged, only those
tuples whose date range contains the effective date of the call (the billing
date) are retrieved (note that this behaviour is not affected by the value of
the PRORATE_ADVANCE_PERIOD configuration attribute). A similar but separate
query is performed to find product/tariff combinations requiring one-off
charge events. Service details are retrieved when an event is being generated.
The service record accessed is the date ranged record which encompasses both
the event start date (required for rating in REPS mode) and the bill run
effective date (required for billing).

If a suitable service does not exist at both the rental start date and bill
run effective date for a product instance rental event, the RGP will either
suppress the event with a warning (REPS mode) or attempt to find a suitable
service using the bill run effective date only (BID mode). If the event is
suppressed it should eventually be generated on a future bill run with an
effective date which does align with a suitable service. This can cause rental
events to be associated with invoices later than expected when using REPS mode
tariffs.

The tariff expression and version information is determined with respect to
the event start date.

When RGP events are rated by the ERT, the charge start date (in BID mode), or
the switch start date (in REPS mode) associated with the event is used to
choose the service, products and tariffs for that event. The event's charge
start date is always set to the effective date of the bill run which generated
the event. If the event is generated as an adjustment the charge start date is
set to the effective date of the current server call.   For recurring tariffs
in Rental event Period Start Date (REPS) mode the switch start date is always
set to the event start date for both normal and adjustment RGP events. Note
that when generating advance events in REPS mode it is possible that the
switch start date will be set to a time in the future.

[Contents]

* * *

## Event Generation for Recurring Tariffs

The algorithm for generating events for a tariff/entity combination is a
complex one and involves looking at such aspects as previously generated
events, the history records of the entity being billed, tariff configuration,
the effective date of the bill run and the settings of several RGP
configuration attributes. The algorithm can be broken down into the following
steps:

  1. Calculate the charge period, that is, the period for which the current bill cycle applies. This can be further broken down into the following steps;   

    1. Calculate the "bill from" date
    2. Calculate the desired end date
    3. Calculate the actual end date
    4. Adjust for the billing window
  2. Determine the active periods, that is, the periods within the charge period where the charged entity is active. These will typically be active for the whole of the charge period.  
For each active period:

    1. Set any fields in the event which RGP automatically calculates
    2. Apply any eligibility expressions from the tariff. If any expression fails the event is NOT generated.
    3. Apply assignment expression from the tariff. These expressions will define values in the generated event.
    4. Merge the event with the previous one if all assignable fields are identical and the events are consecutive.
    5. Calculate the duration of the active period.
  3. Output events to the database

### Calculating the Charge Period

#### Calculating the "bill from" date

If the entity has previously been billed then the "bill from" date will be one
second after the maximum period_end_date of all rows in the
RGP_NORMALISED_EVENT table for this tariff/entity combination. Note that
END_DAY_OF_MONTH is taken into consideration if it is defined. For example, if
the following records exist in the RGP_NORMALISED_EVENT table for this
tariff/entity combination then the "bill from" date will be the logical date
'31'-Feb-2001:

EFFECTIVE_START_DATE| EFFECTIVE_END_DATE| END_DAY_OF_MONTH  
---|---|---  
01-Jan-2001 00:00:00| 30-Jan-2001 23:59:59|  
31-Jan-2001 00:00:00| 28-Feb-2000 23:59:59| 30  
  
If the entity has not previously been billed then the "bill from" date will be
the date the entity first became active. Some entity-specific considerations
are noted in the following table:

Entity| "Bill From" Date  
---|---  
Service| The maximum of

  1. The date the service first became active
  2. The date the product instance the tariff is associated with became active

In effect this means that the charge period for tariffs associated with
companion products will begin on the date that the companion product becomes
active  
Equipment | The date the equipment item was first associated with the product instance and its associated service was active 

#### Calculating the desired end date

To calculate the end date of the charge period, the RGP first calculates the 'desired' end date by adding the advance period (which may be negative if charging in arrears) and the charge period on to the bill run effective date (or some derivation of the bill run effective date).  This calculation is affected by the values of the RENTAL_END_BEFORE_BILL_DATE and ROUND_ENTITY_HISTORY configuration attributes as well as the time component of the bill run effective date as summarised in the following table: | Rental End Before Bill Date| Round Entity History|  DesiredEndDate Formula| Notes| Example*  
---|---|---|---|---  
False| n/a | `EffectiveDate + RecurringPeriod + AdvancePeriod`|  This method is only used when the bill run effective date has a time component of 23:59:59.This method is recommended when doing end-of-month billing. That is, billing on the last of the month and requiring that rental periods include the last day of the month|  EffectiveDate=31 January 2004 23:59:59DesiredEndDate =  31 January 2004 23:59:59 + 1 month + 1 month = 31 March 2004 23:59:59  
True| n/a | `trunc(EffectiveDate)  + RecurringPeriod + AdvancePeriod - 1 second`| With this method rentals are generated until the end of the day prior to the bill run effective date. This method ensures rental charge periods only span a whole number of days.|  EffectiveDate=15 June 2004 10:30:15DesiredEndDate=15 June 2004 00:00:00 + 1 month + 1 month - 1 second = 14 August 2004 23:59:59  
n/a| True|  `trunc(EffectiveDate) + RecurringPeriod + AdvancePeriod - 1
second`|  Unlike entity history start and end dates, the effective date is
always truncated back to midnight time.  It is never rounded upThis method
ensures rental charge periods only span a whole number of days.|
EffectiveDate=15 June 2004 17:00:00DesiredEndDate=15 June 2004 00:00:00 + 1
month + 1 month - 1 second = 14 August 2004 23:59:59  
False| FalseFALSE| `EffectiveDate + RecurringPeriod + AdvancePeriod - 1
second`|  This is the default method when none of the above cases are
applicable.|  EffectiveDate=15 June 2004 17:00:00DesiredEndDate=15 June 2004
17:00:00 + 1 month + 1 month - 1 second = 15 August 2004 16:59:59  
* Assuming a tariff configured with one month charge period and one month advance period 

**Note:** If RentalEffectiveDate is specified, then RentalEffectiveDate is
used instead of EffectiveDate in **DesiredEndDate Formula section** above.

When adding a period specified in months, problems can occur when the day
number of the starting month does not exist in the ending month, for example,
31 January + 1 month = 30 February. This is dealt with by rounding the end
date down to the last day of the target month, treating the event as being for
a full month, and remembering in the generated event what the 'logical day of
the month' that this event was billed up to. The END_DAY_OF_MONTH column in
the RGP_NORMALISED_EVENT table is used to store this information.

#### Calculating the actual end date

Once the RGP has calculated the desired end date, charge periods are
successively added to the "bill from" date to get as close as possible to the
desired end date without exceeding it.  If Pro-Rating is not enabled, this
date will be the period end date.  If Pro-Rating **is** enabled, Pro-Rate
periods are successively added to the end date to get as close as possible to
the desired end date without exceeding it.  If ROUND_ENTITY_HISTORY is set to
TRUE, then a Pro-Rate period of '1 Day' will ensure that the period end date
perfectly aligns with the desired end date.  If ROUND_ENTITY_HISTORY is set to
FALSE and entities are activated and cancelled with sub-day time granularity,
then a '1 Second' Pro-Rate period is required to ensure that the period end
date perfectly aligns with the desired end date.

Note that it is possible that the RGP will not be able to generate an event
for a period that an entity is active if the the Pro-Rate period is not small
enough to 'fill' the period.  Eg. A service is active from 8:00 am. to 10:00
am but the tariff has a Pro-Rate period of '1 Day'. In this case the RGP will
be unable to generate an event to bill for this period.

Note that **Pro-Rating does NOT have any affect on when the charge period
begins**.  In the RGP, Pro-Rating is only used to calculate how close to the
desired end bill date the actual end bill date will be.  For example, if a
product was previously billed up until (or first becomes active on) the 21st
of February 1998, and the tariff has a one month charge period and three
months advance period, and is synchronised with the bill cycle which is run on
the 10th of March 1998, then the desired end bill date will be the 10th of
July 1998.  If Pro-Rating is enabled to an accuracy of one day, then the 10th
of July will also be the actual bill end day.  However if Pro-Rating is not
enabled then the actual end bill day will simply be the 21st of June 1998
(which is the charge period start date plus the three months advance plus the
one month charge).  **It is only the charge period end date which is affected
by Pro-Rating.   **This is a very important point as many people have pre-
conceived ideas as to what Pro-Rating entails which are not compatible with
the way the RGP uses it.  To re-enforce how the RGP uses Pro-Rating, another
example is included below.

If the tariff has a recurring charge period of one month and no advance
period, an RGP run with a bill cycle date of 15 March 1996 00:00:00 will have
a target end date of 14 April 1996 23:59:59. If there is a one month advance
period, this end date would become 14 May 1996 23:59:59. Using the first
example, if the product instance was billed previously to 10 March 1996
23:59:59 and prorating is disabled, the charge period will be 10 March 1996
00:00:00  to 9 April 1996 23:59:59 (i.e. exactly one month). If prorating is
enabled and the pro-rate period is one day, the charge period will be 10 March
1996 to 14 April 1996 23:59:59.

As of version 2.03.32 and later, the RGP only performs bill cycle date pro-
rating if pro-rating is enabled **and** :

  * The difference between the desired end bill date and the charge period start date is greater than one recurring period, OR
  * The charge period start date is less than or equal to the bill cycle date, OR
  * (5.01.20) PRORATE_ADVANCE_PERIOD is set to 1.

Prior to this change, if a tariff was for example configured with pro-rating
enabled, an advance period of zero and a 3 month recurring period, and the
customer was on a monthly bill cycle, then after the initial recurring charge
for a new service the customer would receive a recurring charge each month of
a third of the recurring period charge.  With this change, after the initial
recurring charge, the customer will only receive a recurring charge every
three months equal to one recurring period (similar to if pro-rating was not
enabled in the first place).  The old behaviour can be restored for this
example by setting an advance period of 2 months and a recurring period of one
month and dividing the recurring charge calculations by three.

Fixed-date synchronisation requires the specification of a reference date (the
fixed date) and a fixed-date period (see TARIFF_RECURRING). If a tariff is
synchronised with a fixed date, the RGP will find the nearest day preceding
the bill cycle date that is an exact number of fixed-date periods after the
reference date, then add exactly once advance period and one recurring charge
period to obtain the charge period end date.

For example, given a tariff with a reference date of 10 January 1996 and a
3-month fixed date period, the end dates for billing cycles on the 15th day of
every quarter will be 10 April, 10 July, 10 September etc.

#### Adjusting for the billing window

The configuration attribute GENERATE_PERIOD determines the size of the
'billing window' that the RGP is able to examine history records and generate
events for.  This 'billing window' is from the bill run effective date minus
GENERATE_PERIOD to the end of time.  Any periods outside of this 'window' are
automatically considered ineligible and will not have events generated.  Any
periods that straddle the beginning of the 'billing window' will be 'cropped'
to fit within it.   Eg. a product instance becomes active on the 15-JAN-2004
but the customer owning this product instance isn't billed until 01-JUN-2004.
With a GENERATE_PERIOD of 90 days, the billing window is 03-MAR-2004 until the
end of time.  The period start date of the event will be 03-MAR-2004 (rather
than 15-JAN-2004).

### Determining Active Periods

When determining what periods of an entity's history (product
instance/facility group instance/service/equipment item) are considered
active, the RGP builds a series of timelines and performs a logical 'AND' to
these timelines.  The RGP takes the following timelines into consideration:

#### 1 - Product Instance History

A timeline is built for the history of the Product Instance associated with
the entity.  A Product Instance history period is generally considered active
only when the PRODUCT_INSTANCE_STATUS_CODE field in PRODUCT_INSTANCE_HISTORY
is set to ACTIVE.  However, if the tariff currently being processed has
'Generate Rental Events For Non-Active Status?' checked (ie.
TARIFF_RECURRING.ACTIVE_IND_CODE = NULL) the period is considered active as
long as its status is not CANCELLED, UPGRADED or MOVED.  Eligibility
expressions should be used to further restrict what statuses should should
have events generated.

In retrospective adjustment mode the product instance timeline may be extended
to an earlier date/time than previously billed.  This extension of the
timeline can be disabled by setting the value of the
`ATA_RGP_BACK_DATED_IGNORE` environment variable to `Y`.  However it is
expected that in most deployments this timeline extension should remain
enabled.

#### 2 - Entity History

For entities other than 'Product', a timeline is also built for the entity's
history (as 'Product' entities already have their timelines built in the first
step).  The rules for determining what periods are considered active are the
same as for the Product Instance step except the database tables and field
names are different depending on the entity type:

Entity | Database Table | Entity Status Field Name  
---|---|---  
Product Instance | PRODUCT_INSTANCE_HISTORY | PRODUCT_INSTANCE_STATUS_CODE  
Service | SERVICE_HISTORY | SERVICE_STATUS_CODE  
Equipment Item | EQUIPMENT_HISTORY | EQUIPMENT_STATUS_CODE  
Facility Group Instance | FAC_GROUP_INSTANCE_HIST | FAC_GROUP_INSTANCE_STATUS_CODE  
  
#### 3 - Tariff History

If the tariff has 'Rental Start Date' set to 'Rental Period Start Date' (ie.
the tariff is a 'REPS' mode tariff) the RGP creates a timeline of the tariff's
history. The TARIFF_HISTORY table is queried to retrieve this information.

#### 4 - Tariff's Association with the Product

If TARIFF_CHECK is set to TRUE in the configuration item, a timeline is built
of the periods that the tariff is associated with the product.  The
PRODUCT_TARIFF table is queried to retrieve this information.

If ROUND_ENTITY_HISTORY is set to TRUE in the configuration item, a period
that doesn't cover a whole number of days (ie. whose period start date does
not have 00:00:00 time component and/or period end date does not have 23:59:59
time component) will be rounded to do so before being added to the timeline.
Period start dates prior to 12:00:00 midday will be rounded back to 00:00:00
time on the same day; period start dates 12:00:00 midday and after will be
rounded forward to the following day with 00:00:00 time. Period end dates
prior to 12:00:00 midday will be rounded back to the previous day with
23:59:59 time; period end dates 12:00:00 midday and after will be rounded
forward to 23:59:59 time on the same day. If this results in the period end
date being less than or equal to the period start date, the period is ignored.
If ROUND_ENTITY_HISTORY is set to FALSE, no rounding is performed and periods
are added to the timeline with the period start and end dates as stored in the
database.

NOTE: If period start date is at 12:00:00 midday, the period start date will
be forwarded to 00:00:00 time on the next day and period end date will be
rounded to 23:59:59 on the same day.

A logical 'AND' is performed on these timelines and the result is a timeline
of periods that will go on to have eligibility expressions evaluated and
potentially have events generated. Therefore only periods that exist in all
timelines are considered active and will go on to have eligibility evaluated.
In the process of generating events from these timeline periods, contiguous
eligible periods are combined if all assignable fields are equal and the
current period start date equals the previous record's period end date + 1
second.  However, if the tariff is configured to use the 'Rental Period Start
Date' ('REPS' mode tariff) and the tariff version has changed, then the active
periods will not be joined together, even if all other fields are equal.

[Contents]

### Calculating Durations

The durations output for each active period are given as a fraction of the
recurring charge period of a tariff. For example, a 1 week active period for a
recurring tariff having a period of 4 weeks has a duration of 0.25.

To calculate the duration of a given period, 1 second is added to the period
end date and one of the following formulae is used.  Note that this means date
ranges used for period calculations are inclusive.  The duration calculation
depends on the unit of the charge period of the tariff:

#### Days

> The duration is the number of whole days between the period start and end
> dates plus any day fractions (if one or both of the dates has a time
> component), divided by the charge period; or
>
> `
>
> (DaysBetween(period_start_date, period_end_date) + day_fraction) /
> charge_period`

#### Weeks

> The duration is the number of whole days between the period start and end
> dates plus any day fractions (if one or both of the dates has a time
> component), divided by the number of days per week (7), divided by the
> charge period; or `
>
> (DaysBetween(period_start_date, period_end_date) + day_fraction) / 7 ) /
> charge_period`

#### Months

> If the start day number is less than or equal to the end day number, the
> duration is the difference between the start and end month numbers (taking
> year boundaries into account) plus the difference between their respective
> day numbers plus the day fraction (if one or both of the dates has a time
> component) divided by the number of days per month, or
>
> `(end_month - start_month) + (end_day - start_day + day_fraction) /
> days_per_month`
>
> If the end day number is less than the start day number, the duration is one
> less than the difference between the start and end month numbers (taking
> year boundaries into account), plus the number of days from start day number
> to the end of that month plus the end day number plus the day fraction,
> divided by the number of days per month, or
>
> `(end_month - start_month - 1) + (month_length - start_day + end_day +
> day_fraction) / days_per_month`
>
> Note:
>
>   1. If the day numbers of the start and end dates are the same (start_day =
> end_day) and the time components are the same (start_hour = end_hour,
> start_min = end_min, start_sec = end_sec), the duration is simply the whole
> number of months between the two dates; or
>
> `   (end_month - start_month)`
>
>   2. If both dates fall in the same month (start_month = end_month), the
> duration is the number of days (including fractions) in the period divided
> by the length of the month; or
>
> `   (end_day - start_day + day_fraction) / days_per_month`
>
>   3. If days_per_month = month_length, the second formula is equivalent to
> the first.
>

where:

`charge_period =`

    The recurring charge period as specified on the tariff definition. An integer specifying the size of the charge period in relation to the charge period unit (Days, Weeks, Months)
`day_fraction =`

    `(end_hour - start_hour)/24 + (end_min - start_min)/24*60 + (end_sec - start_sec)/24*60*60`
`start_day =`

    The 'day' component of the period start date.  This may be the 'logical' day rather than the 'real' day if the month is not long enough to hold the desired number of days. Eg. the period start date might be 28 February, but start_day might be set to a value greater than this. If a 'logical' start day is used, it will be the END_DAY_OF_MONTH field in the RGP_NORMALISED_EVENT table for the event generated in the previous month's bill run for this entity/tariff combination plus 1.

    If a 'logical' start day is used and its value is greater than `days_per_month + 1` and 'Average Days Per Month' is NOT being used, then `start_day` is adjusted to `days_per_month + 1` to prevent calculating a duration that includes non-existent days.

`end_day =`

    The 'day' component of the period end date. This may be the 'logical' day rather than the 'real' day if the month is not long enough to hold the desired number of days. Eg. the period end date might be 28 February, but end_day might be set to a value greater than this.  If a 'logical' end day is used it will be the END_DAY_OF_MONTH field in the RGP_NORMALISED_EVENT table for the current event plus 1.

    If a 'logical' end day is used and its value is greater than `days_per_month + 1` and 'Average Days Per Month' is NOT being used, then `end_day` is adjusted to `days_per_month + 1` to prevent calculating a duration that includes non-existent days. 

> Example:
>

>> A duration calculation from 3rd Feb 2023 to '31' Feb 2023 with a
`days_per_month` of 28 would by default be calculated as a duration of (31 -
3) / 28 = 1 when clearly the expected duration should be less than 1. By
adjusting the `end_day` to 29 the calculated duration becomes (29 - 3) / 28 =
0.92857 which reflects the actual percentage of the month covered by the
period.

`start_month =`

    The 'month' component of the period start date 
`end_month =`

    The 'month' component of the period end date 
`start_hour =`

    The 'hour' component of the period start date
`end_hour =`

    The 'hour' component of the period end date
`start_min =`

    The 'minute' component of the period start date
`end_min =`

    The 'minute' component of the period end date
`start_sec =`

    The 'second' component of the period start date
`end_sec =`

    The 'second' component of the period end date
`days_per_month =`

    'Average Days Per Month' as specified on the tariff definition if it is defined and its value is non-zero.  Otherwise, either the number of days in the start or end month is used.  The number of days in the start month is used unless end_day > number of days in start month, in which case the number of days in the end month is used.
`month_length =`

    This is determined by the PRORATE_MONTH_LENGTH configuration attribute.  If this attribute is set to 'Average days per month' and 'Average Days Per Month' is specified and non-zero on the tariff definition, then this value is used as month_length.  Otherwise the actual number of days in the start month is used.  

There are several aspects of configuration that affect the calculation of
durations. Several of these aspects are discussed below:

#### End Day of Month

Some months are not long enough to store the date that the RGP was intending
to store. For example 31-JAN-2005 + 1 month = 30-FEB-2005 23:59:59.  To
overcome this, this date will stored in the database as 28-FEB-2005 23:59:59
and END_DAY_OF_MONTH in the TARIFF_RECURRING table is set to 30.  If
END_DAY_OF_MONTH was not stored, the following month's bill run would have a
period end date of 01-MAR-2005 + 1 Month - 1 Sec = 31-MAR-2005 23:59:59 rather
than 31-FEB-2005 + 1 Month - 1 Sec = 30-MAR-2005 23:59:59 (assuming a charge
period of one month).

It's imporant to take the END_DAY_OF_MONTH field into consideration  when
calculating the duration between two dates.  If either the period start date
or period end date of the period the RGP is caclulating the duration of has an
END_DAY_OF_MONTH specified, then start_day or end_day is adjusted
appropriately (as described above).

#### Average Days Per Month

Consider an event that covers exactly one day (ie. the period start date has
00:00:00 time component and the period end date has 23:59:59 time component,
and start_day = end_day and start_month = end_month), this period could be
interpreted as 1/28th of a month, 1/29th of a month, 1/30th of a month or
1/31st of a month depending on what month (and year) the day falls in.  If
these periods are to be considered the same duration, the tariff definition
should have an 'Average Days Per Month' specified, in which case this value is
used as the month length rather than the 'actual' month length.

As an example, a bill run is run on the first of every month. If a tariff
charges one month in arrears, it charges up to (but not including) the bill
run effective date.   If a service is activated one day before the bill run,
the next bill run should align that service with the bill cycle by generating
an event for exactly one day.   The duration of the generated event can vary
even though each period is exactly one day:

Service Activation Date | Effective Date | Period Start Date | Period End Date | Duration 1* | Duration 2**   
---|---|---|---|---|---  
` 31-DEC-2005 | 01-JAN-2005 | 31-DEC-2005 00:00:00 | 31-DEC-2005 23:59:59  | 0.032 | 0.033  
31-JAN-2005 | 01-FEB-2005 | 31-JAN-2005 00:00:00 | 31-JAN-2005 23:59:59  | 0.032 | 0.033  
28-FEB-2005 | 01-MAR-2005 | 28-FEB-2005 00:00:00 | 28-FEB-2005 23:59:59  | 0.036 | 0.033  
31-MAR-2005 | 01-APR-2005 | 31-MAR-2005 00:00:00 | 31-MAR-2005 23:59:59  | 0.032 | 0.033  
30-APR-2005 | 01-MAY-2005 | 30-APR-2005 00:00:00 | 30-APR-2005 23:59:59  | 0.033 | 0.033  
`

* With no 'Average Days Per Month' specified on tariff definition  
** With 'Average Days Per Month' set to 30.417

#### Prorate month length

When calculating the duration for a pro-rated event that spans the end of a
month (ie. end_day < start_date), the start month can be considered to have a
'real' number of days (ie. the number of days that exist in that month), or
the 'Average Days Per Month' can be used from the tariff definition. Eg. a
product becomes active on 25-FEB-2005 and is being aligned with a bill run on
05-MAR-2005.  When prorating out February, it could be considered to have 28
days (giving 28 - 25 \+ 5 = 8 days), or the 'Average Days Per Month' could be
used  (giving 30.417 - 25 + 5 = 10.417 days).

PRORATE_MONTH_LENGTH gives control over this month length value.  Note that it
is possible to use a month length of 'Days in Start Month' and still use an
'Average Days Per Month' on the tariff definition. In this case the number of
days would still be 28 - 25 \+ 5 = 8 days, but this would be evaluated as
8/30.417 of a month rather than 8/28 of a month.

As another example, consider the following periods, each one starting on the
28th of one month and ending on the 2nd of the following month:

Period Start Date | Period End Date | 'Real' Number of days | Duration 1* | Duration 2**  | Duration 3***   
---|---|---|---|---|---  
` 28-JAN-2005 00:00:00 | 02-FEB-2005 23:59:59 | 6 | 0.194 | 0.178  | 0.197  
28-FEB-2005 00:00:00 | 02-MAR-2005 23:59:59 | 3 | 0.107  | 0.178 | 0.099  
28-MAR-2005 00:00:00 | 02-APR-2005 23:59:59 | 6 | 0.194 | 0.178  | 0.197  
28-APR-2005 00:00:00 | 02-MAY-2005 23:59:59 | 5 | 0.167 | 0.178 | 0.164  
28-MAY-2005 00:00:00 | 02-JUN-2005 23:59:59 | 6 | 0.194 | 0.178 | 0.197  
` * | PRORATE_MONTH_LENGTH = 'Days In Start Month'   
---|---  
| No 'Average Days Per Month' specified on tariff definition  
** | PRORATE_MONTH_LENGTH = 'Average Days Per month'   
| 'Average Days Per Month' set to 30.417  
*** | PRORATE_MONTH_LENGTH = 'Days In Start Month'   
| 'Average Days Per Month' set to 30.417  
  
In summary, if the duration of the event is to reflect the 'real' number of
days in the event, PRORATE_MONTH_LENGTH should be set to 'Days In Start
Month'. However if the the intention is for the duration to be calculated
consistently for months with differing lengths, PRORATE_MONTH_LENGTH should be
set to 'Average Days Per Month'.

Another point to consider is whether there is a requirement that the duration
of a period equals the sum of the durations of the period divided into a
number of smaller periods.

For example, consider the period 01-JAN-2005 00:00:00 -> 31-MAR-2005 23:59:59.
The duration of this period is 4 months regardless of the value of
PRORATE_MONTH_LENGTH or 'Average Days Per Month'.

PRORATE_MONTH_LENGTH | 'Days in Start Month' | 'Average Days Per Month' *  
---|---|---  
Duration(01-JAN-2005 00:00:00 -> 01-APR-2005 00:00:00)  | 4.0 | 4.0  
  
However, if this period is split in two: 01-JAN-2005 00:00:00 -> 04-FEB-2005
23:59:59 and 05-FEB-2005 00:00:00 -> 31-MAR-2005 23:59:59, the duration of the
smaller periods is affected by PRORATE_MONTH_LENGTH.

PRORATE_MONTH_LENGTH | 'Days in Start Month' | 'Average Days Per Month' *  
---|---|---  
Duration(01-JAN-2005 00:00:00 -> 05-FEB-2005 00:00:00)  | 1.129 | 1.132  
Duration(05-FEB-2005 00:00:00 -> 01-APR-2005 00:00:00)  | 2.774 | 2.868  
Sum | 3.903 | 4.0  
  
* 'Average Days Per Month' set to 30.417

A scenario where this could occur is if an event is generated in one bill run,
refunded in the following bill run (due to a rate change) and regenerated by
the RGP, however a change to the entity, tariff or product history causes the
period to be split in two.

To ensure that Duration(A -> C) == Duration(A -> B) + Duration(B ->C),

  1. PRORATE_MONTH_LENGTH = 'Average Days Per Month' 
  2. All tariffs with a charge period in 'Months' should have an 'Average Days Per Month' specified. 

[Contents]

### Event Splitting

Once the RGP has generated a timeline of active periods (see determining
active periods), it iterates through each period and evaluates eligibility and
assignment expressions.  Generally contiguous eligible periods are combined to
form larger periods, potentially resulting in a single event that covers
several charge periods and a prorate period. However the RGP has several
mechanisms for splitting events into smaller segments according to prorate
period, charge period and also arbitrary splitting:

#### Prorate period

If the tariff for which events are being generated has PRORATE_SPLIT_IND_CODE
set to TRUE  in the TARIFF_RECURRING table, then an extra step is performed
after determining the active periods.  The timeline is split according to the
prorate period. That is, the timeline is split so that the prorate period now
exists as its own segment in the timeline.

After eligibility and assignment expressions have been evaluated for each
segment and contiguous eligible events have been combined, the timeline is
again split according to the prorate period.  In this way eligibility and
assignment expressions are evaluated once per segment and it is assured that
the prorate segment will not be combined with other segments again after
evaluating eligibility.

#### Charge period

If the tariff  has CHARGE_PERIOD_SPLIT_IND_CODE set to TRUE in the
TARIFF_RECURRING table, then after constructing a timeline of active periods,
the timeline is split according to the charge period.

#### Examples

In the above diagram, timeline (a) contains one segment for the period from
the bill-from date to the bill-to date which includes a prorate period, charge
periods and an advance period. However after splitting according to the charge
period - timeline (b) - there are 4 segments: one containing the prorate
period and three others of exactly one charge period.  These segments may or
may not have events generated for them depending on the results of the
eligibility expressions.

Note that if the timeline is split according to the charge period then this
also means that it is split according to the prorate period.

After eligibility and assignment expressions have been evaluated for each
segment and contiguous eligible events have been combined, the timeline is
again split according to the charge period, ensuring that each charge period
(and the prorate period) will appear as a separate event.

In the following diagram, a more complicated example is considered. If a
service is re-activated after a period of inactivity, this will result in
multiple pro-rate periods in the final timeline.

Timeline (a) contains one segment for the period from the bill-from date to
the bill-to date which includes two prorate periods, charge periods and an
advance period. If pro-rate splitting is enabled, this timeline is split
according to timelines (b) and (c) into timeline (e). If charge period
splitting is enabled, this timeline is split according to timelines (b) and
(d) into timeline (f).

Timeline (b) represents the segments after splitting according to the entity's
history.

Timeline (c) represents the segments after pro-rate splitting. Note that in
this timeline, contiguous charge periods are merged.

Timeline (d) represents the segments after charge period splitting. Note that
in this timeline, pro-rate splitting is implied.

Timeline (e) is the timeline after timeline (a) has been pro-rate split. It
contains:

  1. The prorate period from the bill-from date to the start of the first billing period,
  2. The period from the start of the first billing period to the date that the service became active,
  3. The prorate period from the date the service was re-activated to the start of the first charge period, and
  4. The merged period formed from the remaining charge periods.

Timeline (f) is the timeline after timeline (a) has been charge period split.
It contains:

  1. The prorate period from the bill-from date to the start of the first billing period,
  2. The period from the start of the first billing period to the date that the service became active,
  3. The prorate period from the date the service was re-activated to the start of the first charge period, and
  4. The remaining distinct charge periods of exactly one charge period.

#### Arbitrary Splitting

An event can be split in two at an arbitrary point via function RentalSplit&.

[Contents]

* * *

## Bill Run Schedules

### Schedule Repeat Type

When creating a bill run schedule, several options are available for
specifiying the repeat interval for creating future tasks:

Month Day

    nth day of the month, eg. the 15th of each month 
Month End Day

    nth last day of the month, eg. the last day of each month 
Month Start

    nth day-of-week of kth week from the start of the month, eg. the tuesday of the second week of each month 
Month End

    nth day-of-week of kth week from the end of the month, eg. the thursday of the last week of each month 

All options except "Month Day" cause problems for the RGP.

The RGP adds periods and calculates durations based on the day number relative
to the start of the month and these options generate a different day number in
each month. _It is strongly suggested that bill cycles for rental tariff
generation always use a repeat type of "Month Day"._

### End of Month Billing

It is possible to do end-of-month billing where the bill run is performed on
the last day of each month and rentals are generated up to _and including_ the
last day of the month and the BGP invoices usage charges up to _and including_
the last day of the month.

For end of month billing, the schedule still has a repeat type of "Month Day"
however the schedule must start on a month with 31 days and the effective date
must have 23:59:59 time component. For months with less than 31 days the
effective date is rounded back to the last day in the month however
EffectiveDayOfMonth& parameter passed into biRentalGenerate& is set to 31 and
the RGP handles this accordingly (see calculating the charge period). Also
note that RENTAL_END_BEFORE_BILL_DATE in the RGP and USAGE_BEFORE_BILL_DATE in
the BGP must both be set to FALSE.

In summary, for end of month billing, the following configuration is
necessary:

  * _Schedule Repeat Type_ set to "Month Day"
  * _Effective date_ must have "23:59:59" time component
  * Schedule must begin in a month with 31 days 
  * _RENTAL_END_BEFORE_BILL_DATE_ must be set to FALSE in the RGP configuration item

[Contents]

* * *

## Retrospective Adjustment

The ADJUSTMENT_PERIOD configuration attribute is used to determine the start
of the adjustment period. All event records for product instances associated
with the current schedule that end after <days> before the effective date of
the current server call are checked and adjusted if necessary. The event
records are retrieved and processed for each product/tariff combination in
order of bill run effective date then bill run Id.

All rental events, including adjustments, must be associated with a bill run
identifier and an effective date to ensure correct billing. The adjustment
period can span multiple bill runs, so adjustment events must be calculated
separately for each bill run spanned by the adjustment period.

Unbilled events and charges which were generated by the same bill run
(typically by a previously run arrears only mode operation) are revoked and
regenerated rather than have adjustments generated. This is possible because
the bill run being re-run was originally performed ahead of the current
billing period and has not yet been run past the rental generation step. Thus
the events and charges have not yet been billed. Such events and charges are
typically those from rental events generated in arrears.

The net effect of revoking and regeneration of unbilled events and charges is
the same as performing retrospective adjustment on current bill run events.
However, by revoking and regenerating whole events, instead of generating
adjustments, it results in less fragmentation of the events and charges when
run multiple times against the same bill run.

Given a product/tariff combination, adjustment events are calculated by
generating four timelines; one for the actual active periods recorded in the
charged entity's table, one for all the periods specified in
RGP_NORMALISED_EVENT (previously generated periods), and two to represent only
the credit and debit periods specified in RGP_NORMALISED_EVENT that were
generated by the current bill run. Note all events generated by QA RGP calls
are ignored for the purposes of retrospective adjustment.

### Retrospective Adjustments for Rental Events Generated by Current Bill Run
(Arrears Rentals)

For periods that exist _only_ in the charge time line (no matching active
period) _and_ were generated with the current bill run ID, the events and
charges are revoked. They are removed from the charge time line, and all
credit and debit periods from the current bill run which overlap or join the
period are also revoked and the inverse effect merged back into the charge
time line. The net effect of this is no credit adjustments are generated
against events generated on the current bill run. By removing the revoked
charges from the charge time line, debit events with appropriate gaps are
regenerated instead.

For periods that exist _only_ in the active time line (no matching period on
the charge time line), all credit and debit events and charges generated with
the current bill run ID which also overlap or join the event are revoked, and
the inverse effect merged back into the charge time line.

No rental eligibility or adjustment expressions are evaluated for events that
are revoked.

For periods that exist _only_ in the active time line with no matching charge
period on the _updated_ charge time line, a normal debit event is generated.
The event is created using the standard rental generation procedure.   That
is, rental eligibility expressions are evaluated and if they return true
rental assignment expressions will also be evaluated.   The event code, and
sub code fields use the tariff's adjustment codes, but otherwise the event
will appear to have been generated by the RGP (not the RAP) process. This step
also effectively regenerates any events that may be required after revoking
any overlapped or joined events above.

For periods that exist in _both_ the active and the updated charge time line
for the current bill run ID, the rental eligibility expressions are evaluated
for each active period to determine if the period is still eligible.   The
eligibility expressions have access to the details of the entity for the
active period as well as the details of the previously generated event.   If
the eligibility expressions return true, then any adjustment expressions are
evaluated. If all the adjustment expressions return true then no action is
required for this period.

If the eligibility expressions return false or any adjustment expression
return false, then the existing debit event for the period will also be
revoked along with any associated charges.  A new debit event is then
potentially created as for standard rental generation via first evaluating the
rental eligibility expressions and, if they return true,  then the rental
assignment expressions.   The rental eligibility and rental assignment
expressions no longer have access to the previously generated event details
which have been revoked.    The debit event is only generated if the rental
eligibility expressions return true.   The event code and sub code fields are
not set to the tariff's adjustment codes.

### Retrospective Adjustments for Rental Events Generated by Previous Bill
Runs

For periods that exist _only_ in the charge time line (no matching active
period) _and_ were _not_ generated with the current bill run ID, a credit
event is generated. The event is copied exactly from the original debited
event. The event code, and sub code fields use the tariffs adjustment codes,
and the duration is negated, but otherwise the events are identical.   No
rental eligibility or adjustment expressions are evaluated for these credit
events.

For periods that exist _only_ in the active time line with no matching charge
period on the charge time line, a normal debit event is generated. The event
is created using the standard rental generation procedure.  That is, rental
eligibility expressions are evaluated and if they return true rental
assignment expressions will also be evaluated.   The event code, and sub code
fields use the tariff's adjustment codes, but otherwise the event will appear
to have been generated by the RGP (not the RAP) process.

For periods that exist in _both_ the active and the updated charge time line
for previous bill runs, the rental eligibility expressions are evaluated for
each active period to determine if the period is still eligible.   The
eligibility expressions have access to the details of the entity for the
active period as well as the details of the previously generated event.   If
the eligibility expressions return true, then any adjustment expressions are
evaluated. If all the adjustment expressions return true then no action is
required for this period.

If the eligibility expressions return false or any adjustment expression
return false, then a credit event is first generated.  The event is copied
exactly from the original debited event. The event code, and sub code fields
use the tariff's adjustment codes, and the duration is negated, but otherwise
the events are identical.  A new debit event is then potentially created as
for standard rental generation via first evaluating the rental eligibility
expressions and, if they return true,  then the rental assignment expressions.
The rental eligibility and rental assignment expressions no longer have access
to the previously generated event details for which a credit event has been
generated.    The debit event is only generated if the rental eligibility
expressions return true.   The event code and sub code fields are not set to
the tariff's adjustment codes.

Retrospective adjustments are cumulative, so the adjustment process can be run
multiple times for the same period without ill effects.

[Contents]

* * *

## Event Generation for One-off charges

Activation, and Cancellation of a product instance, facility group instance,
service or equipment item can result in one-off charges. When multiple events
occur in one billing cycle multiple one-off charges are generated. These are
realised by creating tariffs with the TARIFF_CLASS_CODE field set
appropriately and associating the tariff with products.

### Activation

An event is generated for a product instance, facility group instance, or
service (and associated equipment) **activation** under the following
conditions:

  1. there is an activation tariff associated with the charged entity; 
  2. the charged entity first became active less than ADJUSTMENT_PERIOD days before the effective date of the bill run; and
  3. there is no previous real event (QA events are ignored) for that instance/tariff combination in the RGP_NORMALISED_EVENT table.

If the entity is service or equipment and the activation tariff is associated
with a companion product instance, then point 2 is modified to:

>   1. The earliest date at which the companion product instance became active
> AND the entity is active less than ADJUSTMENT_PERIOD days before the
> effective date of the current bill run"
>

### Cancellation

An event is generated for a product instance, facility group instance, service
or equipment item **cancellation** under the following conditions:

  1. there is a cancellation tariff associated with the charged entity; 
  2. the charged entity first became cancelled less than ADJUSTMENT_PERIOD days before the effective date of the current bill run;
  3. there is no previous real event (QA events are ignored) for that instance/tariff combination in the RGP_NORMALISED_EVENT table; and

If the entity is service or equipment and the cancellation tariff is
associated with a companion product instance, then point 2 is modified to:

>   1. The companion product instance became cancelled less than
> ADJUSTMENT_PERIOD days before the effective date of the current bill run
>

### Notes

1\. The second point mentioned above for both activation and cancellation
events (which limits the period checked for generating one-off events) is
desired behaviour because it is highly probable that many events will be
generated by the RGP.  This could potentially fill database, resulting in the
need to archive off many of the older, previously generated events.  If this
happens all one-off events will be re-generated unless some mechanism is put
in to disable their generation after a certain period.

2\. Also note that activation and cancellation one-off charges can only be
generated once for a charged entity. Reactivation of a cancelled instance will
not generate any charges, noting that the current version of the Singl.eview
Convergent Billing System does not allow reactivation of a cancelled product
instance or service.

3. The status of equipment items as used for generating one-off charges is derived from the status of the service that the equipment item is associated with. Therefore equipment activation charges are generated when the associated service first becomes active. Equipment cancellations have one further level of complexity. Equipment cancellation charges will be generated on the minimum of (a) when the associated service becomes cancelled or (b) when the equipment item itself becomes cancelled.

[Contents]

* * *

## Interim Mode

If biRentalGenerate& is called with the InterimInd& flag set to 1 (TRUE), then
the RGP operates in interim mode while processing this request.  The RGP takes
note of this by setting a flag in the singleton object RgpRunOptions.
RgpRunOptions::GetInstance()->InterimMode() can be called from this point on
to determine if the RGP is in interim mode.  While in interim mode, the RGP
will only process interim bill run tariffs.

When a recurring, activation or cancellation tariff is defined, the tariff can
be defined as an interim tariff in which case the INTERIM_IND_CODE flag is set
in the TARIFF_RECURRING table.

When in interim mode, before processing each tariff, the RGP will check if the
tariff is an interim tariff.  If not, the RGP does not process the tariff, and
proceeds to the next tariff.  If the tariff is an interim tariff, the RGP
processes it normally.

[Contents]

* * *

## Outputting Events

For each eligible active period, the RGP will generate an event and insert a
row in the RGP_NORMALISED_EVENT table. In adjustment mode debit and credit
adjustment events are also generated (see adjustment mode).

The RGP is able to process customers from any partition, however event files
that it generates need to be rated on the CB instance that the customer is
associated with. Therefore the normalised event file needs to be generated on
the CB instance the file will be rated on (which may be different to the CB
instance the RGP is running on).  Therefore the RGP does not populate the
NORMALISED_EVENT or NORMALISED_EVENT_FILE tables directly. These tables are
populated by the rater after the event file has been generated (see
biRgpFileCreate).

The RGP populates the following fields in RGP_NORMALISED_EVENT.  Also listed
are the names of the direct variables associated with the fields (if
applicable) for use in tariff assignment expressions.

Field | Direct Variable | Value  
---|---|---  
RGP_FILE_ID |   | The internal identifier of the rgp normalised event file.  See RGP_FILE  
FILE_RECORD_NR |   | A record number indicating the position of the event record within the file   
PRODUCT_INSTANCE_ID | EventProductInstanceId& | The internal identifier of the product instance associated with the tariff  
FAC_GROUP_INSTANCE_ID  | EventFacGroupInstanceId& | (Optional) The internal identifier of the facility group this event was generated for (only populated for facility group entity tariffs)  
ROOT_CUSTOMER_NODE_ID |   | The internal identifier of the root customer node id associated with the product instance  
CUSTOMER_NODE_ID | EventCustomerNodeId& | The internal identifier of the customer node id associated with the product instance  
SERVICE_ID | EventServiceId& | The internal identifier of the service to be charged for this event   
EQUIPMENT_ID | EventEquipmentId& | (Optional) The internal identifier of the equipment item this event was generated for (only populated for equipment entity tariffs)  
TARIFF_ID | EventTariffId& | The internal identifier of the tariff associated with this event  
VERSION_STR | EventTariffVersion$ | (Optional) The version of with the tariff associated with this event  
BILL_RUN_ID | * | The bill run id that generated the event. For adjustment events this will be the event that generated the original  
QA_IND_CODE |   | 1 {TRUE} if the RGP is currently operating in QA mode. NULL otherwise.  
PERIOD_START_DATE | PeriodStartDate~ * | The start date of the period. See calculating the charge period.  
PERIOD_END_DATE | PeriodEndDate~ * | The end date of the period. See calculating the charge period.  
END_DAY_OF_MONTH | EventEndDayOfMonth& | The day of the month to which the rgp wished to bill for this event. See the description of end day of month in the calculating durations section.  
STATUS_CODE | EventStatus& | The status of the product instance, facility group instance or service over the rental duration period. The entity referred to is dependent on the tariff definition. For rentals associated with equipment, this colum is the status of the associated primary service.   
LAST_MODIFIED |   | The date and time at which the event was generated.  
DURATION | Duration# * | The duration of the active or adjustment period, specified as a fraction of the charge period for the tariff. This field is set to "1" for one-off events. For adjustment events, debit events have a positive duration, whereas credit events have a negative duration.  See calculating durations.  
NORMALISED_EVENT_TYPE_ID |   | The normalised event type id associated with the tariff.  
EVENT_TYPE_CODE | EventTypeCode& | The event type code associated with the tariff. This may be overriden by the assignment expressions  
EVENT_SUB_TYPE_CODE | EventSubTypeCode& | (Optional) The event sub type code associated with the tariff. This may be overriden by the assignment expressions. (Only populated for tariffs with an event sub type code configured)  
SWITCH_START_DATE | SwitchStartDate~ | The date and time used for rating the event. For BIDS mode rentals and one-off charges, it is set to the effective date of the bill run.  
For BIDS mode adjustments it is set to the effective date of the bill run that
generated the event being adjusted. For REPS mode rentals, one-off charges and
debit adjustments, it is set to the period start date of the event.  
For REPS mode credit adjustments, it is set to the period start date of the
event being adjusted.  
For REPS mode if ROUND_ENTITY_HISTORY is set to true:

  1. for credit adjustments, if the switch start date of the event being adjusted is valid (not NULL), then it is the switch start date of the event being adjusted.
  2. otherwise, it is the period start date before any rounding is performed.  
  
* Also note the values of these fields are available via the builtin EPM Rental functions. See builtin EPM functions

The following fields aren't populated directly by the RGP, but can be
populated via tariff assignment expressions. Also given are the names of the
direct variables associated with the fields.

Field | Direct Variable  
---|---  
C_PARTY_NAME | CPartyName$  
C_PARTY_TON_CODE | CPartyTonCode&  
C_PARTY_ROUTE | CPartyRoute$  
FULL_PATH | FullPath$  
CASCADE_CARRIER_CODE | CascadeCarrierCode&  
EVENT_TYPE_CODE | EventTypeCode&  
EVENT_SUB_TYPE_CODE | EventSubTypeCode&  
VOLUME | Volume#  
PULSES | Pulses&  
CHARGE | Charge#  
CURRENCY_ID | CurrencyId&  
RATE_BAND | RateBand$  
GENERAL_[1-20] | General_[1-20]$  
  
[Contents]

* * *

## Real and QA Output

Whether the RGP is running in recurring or adjustment mode, it may be
requested to generate either real or QA events.  Real mode means the events
generated are to be used to generate a real bill, while QA means Quality
Assurance which in turn means the events generated are not for the purposes of
generating a legally binding payable document, but more to see what the bill
looks like at a point in time.

The QA_IND_CODE field is used to indicate that the event is a QA event.  This
field is also used to indicate to the BGP which recurring events to use.  This
is necessary as it possible for multiple QA RGPs to be run for a customer
prior to the BGP begin run.  The BGP needs the bill run Id to determine which
of the QA events to use in generating the QA invoice.

When run in QA mode, the RGP sets the bill run id in the VDA to allow subtotal
functions to fetch the appropriate values.

[Contents]

* * *

## OO Design

### RGP

The principle of the RGP OO design is to abstract the changeable 'modes' of
RGP into virtual hierarchies, thus isolating the behavioural variance.

The main behavioural variances are:

       * Normal generation (RGP) Vs Adjustment generation (RAP)
       * Recurring events Vs One off events
       * Charged entity (Product, Facility Group, Service, and Equipment)
       * BID Vs REPS mode
       * Optional Product Tariff joining table link
       * Charge unit (days, weeks, monthly, fixed date)

These have been implemented in the following class hierarchies respectively

       * RgpGenerator hierarchy - Normal generator versus an adjustment generator
       * RgpGenerator hierarchy - Recurring generator versus an one off generator
       * RgpEntity hierarchy (Product, Facility Group, Service, or Equipment RgpEntity)
       * RgpTimelineStep (tariff time line)
       * RgpTimelineStep (product tariff time line)
       * RgpChargeTime hierarchy

The main loop for generating RGP events can be found in
RGP::GenerateRentals(). The algorithm it uses is as follows:

       * Get the next RgpTariffInfo
       * If in single process mode then
       *     Request the generator from RgpTariffInfo, CreateGenerator()
       *     Start the generator, Generate()
       * else
       *     send the tariff to the next available child

A child process has the following corresponding main loop

       * Wait for tariff to process from parent
       * Request the generator from RgpTariffInfo, CreateGenerator()
       * Start the generator, Generate()

### RgpTariffInfo

RgpTariffInfo class is a 'super' class which joins CUSTOMER_NODE_HISTORY,
PRODUCT_INSTANCE_HISTORY, PRODUCT_TARIFF, TARIFF_RECURRING and TARIFF_HISTORY
tables into one class.  It also contains member variables for recording the
success or failure to apply the tariff, and if failure, the error number and
message.

The main method is CreateGenerator(), which is for creating RgpGenerator's and
configuring them. The algorithm it uses is as follows:

       * If the TARIFF_CLASS_CODE is recurring
         * Create a RgpChargeTime (used to calculate charge period durations) based on the RECURRING_CHARGE_UNIT_CODE:
           * DAY/WEEK - RgpLinearCharge sub class
           * MONTH and not FIXED_DATE - RgpMonthlyCharge sub class
           * MONTH and FIXED_DATE - RgpFixedDateCharge
         * Create the RgpGenerator based on whether this is a RGP or a RAP
           * RGP - RgpRecurringGenerator
           * RAP - RgpAdjustmentGenerator
       * Otherwise must be a one-off
         * Create the RgpGenerator based on whether this is a RGP or a RAP
           * RGP- RgpOneOffGenerator
           * RAP - RgpOneOffAdjustGenerator
       * Create the RgpProductEntity
       * Create the RgpEntity based on the CHARGED_ENTITY_CODE
         * Product - RgpProductEntity (Same instance as previous step, Ie only one)
         * Facility Group - RgpFacilityGroupEntity
         * Service - RgpServiceEntity
         * Equipment - RgpEquipmentEntity
       * Create the time line steps for calculating event periods based on if the TARIFF_CLASS_CODE is recurring
         * If the CHARGE_START_DATE_CODE is REPS add the RgpTariffStep
         * If the charged entity is _not_ product add the RgpProductInstanceStep (stops product being done twice)
         * Add the RgpEntityStep
         * If the PRODUCT_TARIFF table is being used add the RgpProductTariffStep
         * If this is a RAP add the RgpBillRunStep and the RgpAdjustmentStep
       * Otherwise must be a one-off
         * If this is a RGP
           * Add the RgpOneOffStep
         * Otherwise must be a RAP
           * If the charged entity is _not_ product add the RgpProductInstanceStep (stops product being done twice)
           * Add the RgpEntityStep, the RgpBillRunStep and the RgpAdjustmentStep

**Figure 2: RGP Class Diagram**



**Figure 3: RGP Generator Hierarchy**

### RgpGenerator

The main method is Generate(), which is for starting the event generation. The
algorithm it uses is as follows:

       * Create an event timeline by descending through all the time line steps, DoStep() is a recursive method used to perform this.
       * Call the virtual method CreateEvents() when the final step has been applied to the timeline

The generator hierarchy implements the variation between normal recurring,
adjustment, one off, one off adjustment, generation. The generators are built
on the RgpEventGenerator base class which provides most of the functionality,
bar the CreateEvent() method. Each generator builds on the functionality of
the former generator, so the specialisations are fairly light.

An unbounded number of time line steps can be associated with a generator. The
step may loop multiple times, which causes all the steps 'under it' to be run
multiple time. When the final step is reached and run the CreateEvents()
method is used to attempt an event creation for each gap in the time line. The
DoStep() recursive method is used to apply the steps.

The generator also acts as an association hub to facilitate class interacting
with each other. For example when Entity classes need to get info from the
RgpTariffInfo class the GetTariffInfo() method will return the current
RgpTariffInfo class.

The final role of the generator class is to provide some 'global' information,
and control the use of the variables. Most globals for RGP are time marks used
to limit the time line range, or specify what effective time to use for
accessing external info, eg tariffs, expressions.

The RgpRecurringGenerator is used to generate normal recurring events. A
RgpChargeTime member is introduced to the hierarchy to calculate leading edge
events, and charge durations. The SetDayOfMonth() method is used to set the
end day of month field. The value is set and retrieved from the Charge Time
calculator because it is required for duration calculations, and the end day
of month is dependant on prorating values, and charge units.

The RgpAdjustmentGenerator inherits from the RgpRecurringGenerator. When
Adjusting three different types of time lines are dealt with. The credit time
line represents charges issued that are not matched by the charges required
time line. The debit time line represents charges required that are not
matched by the charges issued time line. The expression compare time line
represents periods where charges have been issued and charges were required.

       * CREDITS - Have identical values to the debit they are cancelling, except for event type codes (adjustment type codes are used), and duration which is negated to indicate a credit.
       * DEBITS - Are generated in the same manner as normal debits, except no leading edge calculations are required (the end date is known), and adjustment event type codes are used.
       * EXPRESSION_COMPARE - Events are 'checked' for correctness by using the adjustment expressions. If an adjustment expression fails a credit and a debit event are generated.

The RgpOneOffGenerator is very similar to normal recurring events, except
duration calculations are simplified (always 1 sec). The TariffClassEnum
member is used to indicate whether activation or cancellation events are being
generated.

The same relationship between RgpOneOffAdjustGenerator and RgpOneOffGenerator
exist, as for RgpAdjustmentGenerator and RgpRecurringGenerator. If multi
inheritance wasn't such a compiler risk it would have been used.

**Figure 4: RGP Entity Hierarchy**

### RgpEntity

The RgpTimeLine hierarchy provide an abstract framework that is used by the
RgpTimeLineStep classes to build a gap time line The time line represents
periods where the 'entity' (in this context entity means more than just the
product / fac group / service / equipment quartet) is 'on'.

The main interface to this class hierarchy is the GetNextTimeLine() method. If
multiple time lines can be generated for the entity (this is the case when
multiple entity Ids need to be examined) a StepCode of LOOPING is returned.
This informs the calling Step class that more time lines are available.

Eg: Multiple facility groups charges can be generated for one product. A time
line for each fac group id is generated. Only one product_tariff time line can
be generated for each product tariff pair. So the fac group time line may loop
(different fac group id per time line), but the product_tariff time line will
always be singular - no looping.

The time line generation procedure is simple. Use the virtual method
SetFirst() to move to the first 'on' period in the hierarchy - this is where
is the database is accessed. Virtuals GetStart() and GetEnd() are used to read
the bounds of the current period. SetNext() is used to move onto the next
period. SetFirst(), and SetNExt() are usually implemented at the bottom of the
RgpTimeLine hierarchy.

The SetExternal() method is used to make available information relating to the
current time line to associated classes. When generating a multiple id time
line the first period of the next id must be retrieved to determine the end of
the current id. Therefore we need to cache any information that is required
about the first time line, eg Id. SetExternal() loads this cache.

The virtual method GetInternalId() is used to determine if the end of one Id
time line has been reached (access sql should sort by id). GetId() should be
used to determine the Id of the current time line. (In a perfect world
GetInternalId() would be protected, but we cannot do this - try it and the
compiler will explain)

The RgpOneOffTimeLine class is used to generate time lines for recurring
events. There are another class of events - one off events. These events since
2.0.2 have a period - 1 second. This enables adjustments to be created for one
offs. The RgpOneOffTimeLine class is conceptually very similar to RgpTimeLine.

       * SetFirstOneOff() = SetFirst()
       * SetNextOneOff() = SetNext()
       * SetExternalOneOff() = SetExternal()

For time line class derived from RgpTimeLine a member field oCurrent is
normally used to hold the contents of the current sql retrieved row. This was
done because there is often auxiliary information required. One offs are
simpler. Only the Id and the time is required for all sub classes. So members,
and Set()/Get() methods have been defined at this level.

       * SetId() - Sets the entity Id (SetExternalOneOff() is basically a wrapper for this)
       * StoreValues() - Get the current period from the access query
       * ResetValues() - Clears the values, used for safety when the end of a query is reached.

RgpEntity is used as a base class for any chargeable entity (currently the
product/fac group/service/equipment quartet). A charge entity must get time
lines relative to it's product instance - a link to product is always present
in any retrieve periods sql.

Additionally entities have generated rgp events, which represent where the
entity has been charged to. RgpEntity provides a framework for calculating
this 'paid to' date. The methods used to do this are:

       * FindBillStart() - Find the last real rgp event (QA events are ignored) record for the entity
       * FindActivation() - If never charged, then find the activation date

GetId() and SetId() are required for time line base classes (see their
descriptions).

All charge entities are associated with tariffs, so GetTariffId() and
SetTariffId() are provided to simplify tariff id access.  
  
Enities require information from other classes. The RgpGenerator class acts as
a hub to other classes. Entities use this association to navigate to all other
classes. GetGenerator() retrieves the association.

Often sql must be generated dependent on which type of charge entity is being
used. AddWhereSnippet() is used to generate a where clause specific to each
entity type. It is not used by the RgpEntity hierarchy.

RgpTariff acts like the time line generation aspect of a charge entity, with
two variations.

The time line is *not* split on active/inactive periods (tariffs are always
active, the product_tariff tables is used to 'turn them off'). The time line
is split on version changes. Hence the Ver access methods.

The more significant variation is the Load() method. When events are generated
some tariff info must be loaded that are effective for the event time.
Therefore the tariff history is generated and *retained* in memory. The Load()
method provides an access to the history. It uses the same SetFirst(),
SetNext() methods that the time line generation class uses.

  
The RgpNormalisedEvent class is a fairly normal single time line class. It has
the cached history Load() functionality as described in RgpTariff. The other
variation in this class is the UseBillRun methods and variable. When looking
for one off events bill runs are ignored, so this interface is provided to
adjust the SQL statement.

RgpNormalisedEvent generates different SQL for each charge entity, so SQLQuery
caching is not used - a new query is created each time. It would be possible
to 'unroll' the SQL into for the four charge entities, and this would need to
be duplicated for the bill run on/off variation, hence eight queries if
improved performance was required.

**Figure 5: RGP Time Line Step Hierarchy**

### RgpTimelineStep

A time line step represents how a time line is modified by various entities. A
RgpTimeLine class is always used to fetch a time line for the entity, which is
usually just ANDed with the current time line. However some steps (currently
adjustment and one offs) can be more complex. But note that once the step has
modified the time line the generator continues in a uniform fashion. The
AdjustTimeLine() method provides the interface to this behaviour.

The rest of the RgpTimelineSteps class if used to facilitate a 'hook' back
into the generator class. An ID is passed back to the generator so the hook
treated differently for different steps.

The tariff time line is broken up by tariff version changes. It uses the
RgpTariff entity class.

The product tariff time line shows when the tariff was active with respect to
the tariff. The product instance time uses the RgpProductTariff entity class.

The product instance time line shows when the instance was active. It
shouldn't loop. The product instance time uses the RgpProductEntity entity
class.

The entity time line shows when the entity was active for the particular.
product instance. It may loop, one line per entity ID. The entity time uses
the RgpEntity entity class, which will be an instance of
RgpFacilityGroupEntity, RgpServiceEntity, or RgpEquipmentEntity (Note the
Product Instance is always present, and has it's own step).

The bill run time line shows the period the bill run was generating events for
the product instance. It shouldn't loop. The bill run time uses the RgpBillRun
entity class. Only real events are included in the bill run time line, no QA
events are included.

The adjustment step is more complex than just ANDing an entity time line with
the current time line. The previously generated event time line is created
using the RgpNormalisedEvent class. This time line is EXORed to create a
CREDIT, and DEBIT, time line. The time line is then further modified to revoke
events generated by the current bill run that overlap the required CREDIT and
DEBIT events, with the inverse effect of the revoked events merged back into
the time line. The resulting time line is then EXORed again to recalculate the
required CREDIT and DEBIT events. Also the previous event time line is ANDed
to produce the EXPRESSION_COMPARE time line.

The RgpOneOffStep step is a bit like the adjustment step in that it gets a one
off time line for the entity and compares it to the previously generated one
off charges. A time line representing debits are then generated.

The RgpOneOffAdjustStep step is functionally identical to the
RgpAdjustmentStep. The only difference is that one off time lines are used.
See the RgpAdjustmentStep.  

**Figure 6: RGP Charge Time Hierarchy**

### RgpChargeTime

The main interface methods for RgpChargeTime are Init(), CalcEnd() and
CalcDuration(). All other public methods are simple configuration methods, of
data access methods.

Init() configures the charge time class from the tariff info super class. This
method is virtual so sub classes can extract differing info from the tariff.
CalcEnd() calculates the 'leading edge' of the current tariff with respect to
the charge entity. CalcDuration() calculates the number of charges the event
has incurred based on the charge period, and the charge period unit.

Linear charge is used for day and week charge units. The algorithm for
calculating the 'leading edge' date - CalcEnd() - is fairly generic, and is
reused my Monthly charge. The AddPeriod() and CalcDuration() methods are very
simple for weeks, and days.

Monthly charge specialises the CalcDuration() and AddPeriod() methods defined
in Linear charge. Months vary in length, but are are charged equal amounts.
This basic paradox leads to more complex algorithms than linear calculations.
Three points need to be kept in mind. Always try and keep things in whole
month chunks. Provide flexibility when charging for partial months. And try to
keep a consistent approach to month length variation. This final point has
been dealt with by introducing the oDayToChargeTo (AKA end day of months, AKA
desired day) member. When a month is too 'short' for the desired day, the
desired day is stored, so the _intention_ of the charge is retained. This
clarifies ambiguities that arise when this information is not retained

Monthly Pro-rate charge descends from Monthly and specialises CalcDuration,
performing extra operations to handle pro-rating. Splitting Monthly and
Monthly Pro-rate into two classes helps protect the more simple monthly
calculation from errors introduced by changes to the more complicated monthly
pro-rating calculations.

Fixed Date charge uses a different algorithm for calculating the 'leading
edge' (see the RGP SAS), but the CalcDuration() and AddPeriod() methods of
Monthly Charge are reused without specialisation.  

**Figure 7: High Level Event Generation Event Trace**

The above event diagram shows are very conceptual overview a RGP generation.

[Contents]

* * *

## Section 3 - Server Multi-process Considerations



### Server Considerations

The RGP runs as a Tuxedo server.  This gives rise to several issues.  

**Forking  
**When a tuxedo server initialises, all shared memory and IPC pipes are made
ready by Tuxedo prior to the server's code being executed.  Should the server
then fork another process, the child process will duplicate the pipes and
shared memory handles causing confusion for the Tuxedo bulletin board in its
communication with the server.

For this reason, when the RGP server forks its child processes, it uses the
fork followed by the exec function.  This replaces the entire process space of
the child with the new executable.  The new executable is the trergp_client
which is the same as the server in event generation functionality but
different in that it receives processing instruction from the RGP server via
an IPC pipe.

Once the fork execs have taken place the RGP server assumes the role of
distributer and load balancer, and the child processes perform the task of
generating the events.

If no forking is necessary, the RGP server generates all events itself.

**Configuration Loading**  
When the server starts, apart from forking child processes, it also load the
relevant configuration information.  Because a fork exec is being used this
configuration does not persist in the chilld process's data space.  The
configuration details are therefore sent to the child after forking via a pipe
command message (RgpConfigCmdMsg) which is created using the RgpConfiguration
settings.

**Call Parameter Communication**  
Apart from configuration information, the child processes will also need to
know the effective start date, the effective day of month, real or QA mode and
rental or adjustment mode information.  Each client will also need to know the
bill run Id for each event that it outputs.  For this reason, at the start of
each call, each child process receives an RgpRunOptionsCmdMsg message which
contains this information.

#### Cache Access

Each RGP child process attaches to the CNM and SCM caches and registers their
built-in functions. In this way each RGP child process has access to SCM and
CNM built-in Functions.

#### Function Access from the child process

As the child process is created from the parent and established its
treConnection, it will have the operator name of tpsysadm, and this will not
be changed from call to call, as the only mechanism for doing this would be to
send a message to the child to disconnect and reconnect as the operator name
of the caller of the biRentalGenerate&() function.  This process would
introduce a considerable cost of execution, and is therefore not done.  As
this is only an issue for function access (FUNCTION_ROLE_MAP), the simplest
solution is to allow tpsysadm to have access to the custom tariff and
eligibility functions.  The UTP_RGP data consists of several functions that
require this access.

**Cache Purging  
**Purges are passed through to child processes.

**Error Handling**  
See biRentalGenerate's decription of error handling.

**Concurrency Control**  
See Customer Hierarchy Locking.

**Basic Server and Client Class Design**

                   

**Figure 8:   Server Class Design**

**Server Controller Class  
**Responsible for creating a list of processing nodes and liasing with the
database package to get child nodes, perform locking and updating the
CUSTOMER_NODE_BILL_RUN table.   Passes Processing Nodes to the Generation
Controller for processing. Updates root nodes with error counts and is
responsible for aborting a run or hierarchy if error counts reach thresholds.

**Processing Node Class**  
Groups the Customer Node Id with the status, Root Customer Node Id, Processing
Status and any error messages for the Customer Node Id.  Processing Node
objects are passed to the Database Package and the Generation Controller
object.

**Generation Controller Classes  
**There are four Generation Controller classes.

> **Base Generation Controller Class  
>  **This class contains common pure virtual methods used  for generating
> events for a given customer node.
>
> **Generation Controller Class  
>  **Used when the server is running in single process mode. For each Customer
> Node Id passed, this generator controller issues a command to the RGP Engine
> Package to generate events.
>
> **Generation Controller Server Proxy and   Generation Controller Client
> Proxy Classes**  
>  Used when the server is running in multi-process mode.  This proxy class
> talks to the client proxy class via the Multi-process framework package. The
> client proxy receives the message and issues the appropriate command to the
> RGP Engine framework  
>

**Single Process Server Sequence**

**Figure 9: Single Process Server Sequence**

**Notes:  
**Although the calls GenerateRentals and GetResults could be combined, they
are made separate to allow a greater degree of code sharing between the single
and multi-process servers. See the notes for the Multi-process Server Sequence
diagram below for more information.

**Multi-process Server Sequence**

**Figure 10: Multi-Process Server Sequence**

**Notes:  
**The GenerateRentals and GetResults calls are separate. At the same time
SendToIdleChild is called, the tariff details are placed in a list with an
unfilled space for the result of the call.  When the child reports completion,
the success/fail status and any error messages are placed in the same list
against the tariff.  The call to GetResults retrieves the result details which
the server uses to updates appropriate tables and check error thresholds.

If multi-tenancy is in use, the effective tenant is not propagated to child
processes and therefore child processes will not run with an effective tenant.
For this reason, if multi-tenancy is enabled, the RGP should be configured not
to use child processes, as the child processes will not be able to correctly
retrieve tenanted configuration.

**Multi-process Client Sequence**

**Figure 11: Multi-Process Client Sequence**



### Multi-process considerations

The RGP is capable of running multiple processes in order to process faster.
The following is a breakdown of the major classes and methods used to achieve
this, as well as a description of the algorithm involved in multi-processing.

#### Multi-process Class Diagram

                            

**Figure 12: Multi-process Class Diagram**

Please note that the above class diagram represents the objects in one
process.  That is, the Child Process in the above diagram is really a Child
Process class and exists in the parent process, not the child.  See the class
explanations below for more details about this.

Focussing for a moment on the multi-process package, here is a sequence
diagram which explains how the package operates.

#### Multi-process Framework Sequence Diagram

                 

**Figure 13: Multi-process Framework Sequence Diagram**

#### Process Controller

This class handles the technical details involved with forking, execing,
killing and communication between the child and parent processes.

Operations begin when the application requests the process controller object
to fork some child processes.  At this point the process controller forks the
required number of child processes, and for each child process created it
creates a Child Process object and one pipe for communication between the
parent and child processes. Because the parent process is a Tuxedo server, the
fork must be followed by an exec call.  This removes all references to
Tuxedo's shared memory and pipe handles. The child process immediately re-
establishes communications with the parent via the pipe handle passed as a
parameter to the child client executable on startup.

Communication from the parent process to the child process is controlled by
this object.  When the application wishes to send a message to the child
process it creates the message and passes it to the process controller for
sending.  The process controller finds an appropriate Child Process to
communicate with by checking its own internal representation of the child
processes it has spawned.  This representation is a vector of Child Process
objects.  Once the right Child Process object has been located, the message is
sent to the child process by calling the Child Process object's write method.

A set of pipe file descriptors is maintained in the Process Controller object
and this set is used to read from the child processes.  When a read is
required, a select is performed on this set of file descriptors, this select
waits for a pipe to become ready for reading.  Once a pipe is ready for
reading, the Child Process object owning the pipe is identified by checking
which pipe file descriptor is ready, and which Child Process object owns that
descriptor.  Once the Child Process object ready for reading has been
identified, a read takes place by calling the Child Process object's read
method.

Both child processes (not object) and parent processes have a functional
Process Controller object. When a child wishes to communicate with its parent
it uses the pipe directly owned by the Process Controller object.  The Process
Controller object has WriteToParent and ReadFromParent methods for this
purpose.

When it is time for child processes to die, the Process Controller's
KillChildProcesses method is called.  The Process Controller then sends each
child process a shutdown message, via the pipe.  The child process responds
with a terminating message and dies.  Once the Process Controller has received
terminating messages from all child processes, the Process Controller will
wait for each child process to terminate and then return.

#### Child Process

The Child Process class represents the child process forked and contains the
pipe class for that child as well as PID and status. This is not to be
confused with the child process.  The Child Process class is a representation
of the child process and lives within the parent process.  The parent process
creates one Child Process object for each child process it forks.

The Child Process class has Write and Read methods which the parent process
uses to communicate with the child process via the Pipe object.

#### Pipe

The Pipe class encapsulates the inter-process communications.  It contains two
unnamed half-duplex pipes used for two way communication. Each Child Process
object has one of these Pipe objects to communicate with the child process.
The process controller object has a Pipe Object also, but it is only used to
communicate with the parent process and so is not useful if the process is not
a child.

It has two main methods, Write and Read.  It also has an InitChild and
InitParent method.  These are called after forking, the InitChild method is
called in the child process and the InitParent method in the parent process.

#### RGP Messages

The messages sent between parent and child processes are "smart" messages,
based on the Command pattern (Gamma et al).  The basis of the message class is
the RgpCmdMsg command message class, that provides the means of creating the
message, encoding it as an IPCMessage (suitable for writing to and reading
from pipes) and executing its command.  The general idea is that the command
messages know how to perform their executions and actions, so the
communications protocols do not need to have specific sequences coded into
them.  The sender creates a message with the data as required for the data-
based constructor, and the constructor calls Encode(), which will encode the
message into an IPCMessage object.The simplest message is just its type
(RgpCmdMsg::RgpCmdMsgType) which acts as a flag.

The receiver of the message has a process loop that reads an IPCMessage from
the pipe, and passes this message as a parameter to the RgpCmdMsgFactory,
which will create the appropriate RgpCmdMsg based on the message type and
return a pointer to it.   The constructor of the RgpCmdMsg which takes an
IPCMessage parameter calls the Decode() member function to convert the
IPCMessage to the message-specific data.  The process loop then calls the
returned message Execute() function.

If the RgpCmdMsg requires access to external objects, they can be connected by
creating and registering an RgpCmdMsgAction based object via the
RgpCmdMsgFactory::SetMsgAction().  The RgpCmdMsgFactor will attach the
registered action to the created message, so the message Execute() function
can call the attached oAction->Act() member function.

Command messgaes that operate on global (singleton) objects do not normally
require an action, as the objects to manipulate are visible in the Execute()
function.

#### RGP Controller

The RGP Controller class brings everything together. It owns a Process
Controller object, a Message Encoder object and a MessageDecoder object.  The
RGP Controller implements the inter-process protocol, of forking, setting
ENMs, when to send messages, when to receive messages, what each message
means, and the protocol of terminating the child processes.  This protocol
will change from system to system, the messages and their meaning will also
change from system to system.  That is why the RGP Controller class
encapsulates all that is specific to the RGP, while still having knowledge of
the inter process controlling structures.

For each ENM that a child process may use the RGP object calls the RGP
Controller's AddENM method.  This builds a list of ENMs in the RGP Controller
object.   When the RGP Controller object is instructed to fork processes, it
uses this list to allocate an ENM process to each child RGP process.



The following two sequence diagrams illustrate how the parent process uses the
RGP controller to interface to the multi-process package.

#### Parent To Child Sequence Diagram

                  

**Figure 14: Parent To Child Sequence Diagram**

#### Parent From Child Sequence Diagram

####  

**Figure 15: Parent From Child Sequence Diagram**





The remaining two sequence diagrams illustrate how the child process uses the
RGP controller to interface to the multi-process package.

#### Child To Parent Sequence Diagram

                 

**Figure 16: Child To Parent Sequence Diagram**

#### Child From Parent Sequence Diagram

                 

**Figure 17: Child From Parent Sequence Diagram**

#### Number Of Processes

The RGP spawns the number of child processes specified by the configuration
attribute CHILD_PROCESSES.  If this attribute equals zero or is not present
then no child processes are spawned, and the RGP will run in single process
mode. This attribute may be over-ridden by the command line option -c
<number>.  Where <number> is the number of child processes to be spawned.
Once again a value of zero (-c 0) means the RGP will run in single process
mode.  If the -c option is specified the CHILD_PROCESSES attribute is ignored.

#### ENM Mapping

Which ENM each child process is assigned is decided using a round robin
approach, choosing ENMs from the ENM_PROCESS_LIST in the RGP configuration.
For single process servers, the Tuxedo server id of the trergp is used to
calculate which ENM to use by performing a modulo operation against the number
of ENMs configured.

The ENM_PROCESS_LIST is a list of positive integers separated by commas.  Each
integer must map to an existing ENM as defined by the ENM's sequence number
attribute.  That the mapping is correct and the ENM mapped to is valid is
confirmed using the biConfigItemFetchByType& function.  An EPM script using
this function to retrieve attribute details performs the following tests:.

      1. Each ENM process in the list exists as a configuration item.
      2. For each configured ENM it has an INPUT_METHOD of file.
      3. For each configured ENM it has a normalised event file type (as of the current date and time) that supports the native decoding format.

_Example 1_ :  If 6 child processes (CHILD_PROCESSES = 6) are required and the
ENM_PROCESS_LIST is "1,2,3" then the processes to ENM mapping will be

**Child Process** | **ENM**  
---|---  
1 | 1  
2 | 2  
3 | 3  
4 | 1  
5 | 2  
6 | 3  
  
_Example 2_ :  If no RGP child processes (CHILD_PROCESSES = 0) are required,
the ENM_PROCESS_LIST is "11,12,13" and trergp Tuxedo server ids are "104, 105,
106, 107".  The ENM mapping will be:

**trergp server id** | **Index** | **ENM**  
---|---|---  
104 | 104 % 3 = 2 | 13  
105 | 105 % 3 = 0 | 11  
106 | 106 % 3 = 1 | 12  
107 | 107 % 3 = 2 | 13  
  
In a multi-instance environment, the assignment of ENMs to child processes is
handled a little differently. Each child process must be assigned an ENM for
each instance where rating may take place. This is accomplished by including
at least one ENM from each instance where rating may occur in the
ENM_PROCESS_LIST. If more than one ENM from a given instance is included in
the ENM_PROCESS_LIST, they are assigned in a round robin process to each
successive child process. While not required, it is recommended that the ENMs
be grouped by instance in the ENM_PROCESS_LIST.

_Example 3_ : 6 child processes (CHILD_PROCESSES = 6) are required and rating
may occur on one of two instances (MASTER and BACKUP). ENM 1, 2 and 3 are
configured to run on the MASTER instance, while ENM 4 and 5 are configured to
run on the BACKUP instance. If the ENM_PROCESS_LIST is set to "1,2,3,4,5", the
child process to ENM mapping will be:

**Child Process** | **ENMs**  
---|---  
1 | 1 and 4  
2 | 2 and 5  
3 | 3 and 4  
4 | 1 and 5  
5 | 2 and 4  
6 | 3 and 5  
  
_Example 4:_ No RGP child processes (CHILD_PROCESSES = 0) are required but
rating may occur on one of two instances (MASTER and BACKUP). ENM 1 and 2 are
configured to run on the MASTER instance and ENM 3 is configured to run on the
BACKUP instance. If the ENM_PROCESS_LIST is set to "1,3" then the processes to
ENM mapping will be: No child processes, one main process with ENMs 1 and 3.

_Example 5:_ As for Example 4, except that the ENM_PROCESS_LIST is set to
"1,2,3". The processes to ENM mapping is the same as for Example 4.

If a situation arises where a child process does not have an ENM assigned to
it for a particular instance and the child process processes a tariff for a
customer that belongs to that instance, an error is raised and the entire
customer hierarchy currently being processed is failed (see Error Handling).

#### Multi-tenancy

If multi-tenancy is in use, the effective tenant is not propagated to child
processes and therefore child processes will not run with an effective tenant.
For this reason, if multi-tenancy is enabled, the RGP should be configured not
to use child processes, as the child processes will not be able to correctly
retrieve tenanted configuration.

#### Flow of execution

The RGP begins and reads its configuration values from the database. It calls
the process controller to create the number of required child processes. Just
before each process is forked, the relevant ENM (or potentially multiple ENMs
in a multi-instance environment) is set for the child process.

Once the child processes are ready the parent process opens the main query and
for each row returned, encodes the row information in a message and sends it
to the next available child.

The child process, once started waits for the parent to send it a tariff to
process. Once received, the child then processes the tariff and reports itself
to the parent as being once again idle.

With regard to file output, each child appends its process Id to the filename
it creates.  There is a maximum number of events that can go into one file (as
specified by the configuration attribute MAX_EVENTS).  If a child fills a file
and then receives another tariff which generates yet another event, the child
process creates the actual physical event file (see biRgpFileCreate&), sends
the completed file immediately to the appropriate ENM (see
biEnmFileProcessByName&) and continues processing without waiting for the ENM
to complete. Note that the call to biRgpFileCreate& is synchronous, ensuring
that the call to biEnmFileProcessByName& will not occur until the physical
file has been fully created.

In a multi-instance environment, if a child process receives a tariff which
"belongs" (by virtue of the customer the tariff is associated with) to a
different instance than the previous tariff it processed, and the newly-
recieved tariff generates at least one event, the child process immediately
closes its currently open file and sends it to the appropriate ENM (see ENM
Mapping) for processing (note that this call, to biEnmFileProcessByName&, is
performed synchronously). This occurs even if the file isn't full yet. The
child process then opens a new file to contain the events for the newly-
received tariff.

When the child process is requested to close, it checks for an open, non-empty
file and if one is present, it closes it, creates the actual physical event
file, sends it to the appropriate ENM and then waits for the ENM to complete.
Once this has occurred the child process will terminate.

Once all of the records have been processed and all children have reported
themselves as being idle, the RGP instructs its children to die, waits for
them to die and completes.

#### Termination

On termination the parent process (which is the server) receives an
instruction from Tuxedo to perform termination routines.  Upon receiving this,
the server issues a message to all children to terminate.   Each child then
responds with an acknowledgment of the message and terminates.   The parent
process waits for all children to terminate and then returns control to Tuxedo
for shutdown.

#### Signals

The following signals are handled by the RGP:

SIGCHLD _(parent trergp process only)_

    Removes the child process details from the list stored in the parent and then checks for other dead child processes.  If a shutdown was not expected (ie. the child process had not been instructed to terminate): 
      1. Logs a warning message for each child process that terminated abnormally 
      2. Terminates any remaining child processes
      3. Re-forks all child processes 
      4. Returns immediately with error status and error set to `'<E03296> rgp: Child Process <1:ProcessId> has terminated abnormally' (`if received while processing a biRentalGenerate& call)
SIGTERM

    If received by the parent trergp process while processing a biRentalGenerate& call: 
      1. Returns immediately from the biRentalGenerate& call with the error `'<W03275> rgp: Signal SIGTERM received'`

If received while the trergp server is idle:

      1. Terminates all child processes
      2. Terminates

If received by a child process:

      1. Commits outstanding database changes 
      2. Terminates
SIGINT

    See SIGTERM
SIGUSR1

    Dumps a memory report to the $ATA_DATA_SERVER_LOG directory with the name rgp.<pid>.mem. If the file doesn't exist, it is created, otherwise a memory dump is appended to the end of the file.
SIGUSR2

    Toggles RGP tracing.

[Contents]

* * *

--------------------------------------------------
## Contents

    Overview
    

    Configuration
    Service biIGP

    biAdjustmentImageGenerate&
    biAdjustmentImageGenerate& (2)
    biInvoiceImageGenerate&
    biInvoiceImageReGenerate&
    biReportImageGenerate&
    Service biIGPTran

    [bi]DocumentImageGenerate@
    [bi]DocumentImageInsert&     [bi]DocumentImageFetchById&
    [bi]DocumentImageUpdate&
    [bi]DocumentImageDelete&
    Event biPurge     EPM Interface

    Remote TRE Functions

    AdjustmentImageGenerate&
    AdjustmentImageGenerate& (2)
    InvoiceImageGenerate&
    InvoiceImageReGenerate&
    ReportImageGenerate&
    Purge/Trace Functions

    biTrcIGP&
    DerivedTablePurge&
    FunctionPurge&
    IGPTrace&
    InvoiceMessagePurge&
    ReferenceTypePurge&
    ReferenceTypePurgeById&
    ReferenceTypePurgeByLabel&
    SubtotalPurge&
    TariffPurge&
    TemplatePurge&
    Template Processing Functions

    InvoiceAccountPartitionNr&
    [bi]InvoiceReportAccounts&
    InvoiceImageSuppress&
    TemplateCall&
    TemplatePrint&
    Miscellaneous Functions

    LoggerReload&
    Invoice Image Generation

    Multi Process Mode
    Image Generation
    Template Processing
    Evaluating Templates
    Using Tariffs and Subtotals in Templates
    Caching
          Purging
    Memory Images
    Dunning Letters
    Statistics

    IGPStats?{}
    IGPLogStatistics&
    Signals

* * *

## Related Documents

    Detailed Design Document for the IGP
    Unit Test Plan for the IGP

* * *

## Overview

The Invoice Generation Process (IGP) module consists of two Tuxedo server
processes, treigp and treigp_tran.

The treigp server is a non transactional server that generates images for
invoices, adjustments and reports using templates, the invoice information
generated by the Bill Generation Process (BGP), adjustment details created by
the biAdjustment service and other data (for reports).   The treigp functions
execute in the biIGP service.

The treigp_tran server is a transactional server that generates document
images for a given template and set of parameters and values. The treigp
functions execute in the biIGPTran service.

Templates contain TeX, XML or other source embedded with names of templates
and arbitrary EPM expressions.   To generate the output document, the IGP
replaces the EPM expression with their value in the template context and
replaces the template names with their evaluated contents.   Each template has
a template type. The set of template types and their hierarchy is static and
defined by the reference codes of the **TEMPLATE_TYPE** reference type.  Each
template type is associated with a database view and is able to access the
column values of that view through the use of embedded expressions. Column
values of views associated with type of parent templates can also be accessed.
Templates have an optional SQL WHERE clause that can be used to restrict the
data seen in the view.

The hierarchical structure of an image is formed by embedding references to
child templates in a parent template.  An invoice image is created using an
invoice template hierarchy where the root template type is **Invoice or
Statement Image**.  The root template for each invoice is determined by an
invoice format associated with the customer node.  An adjustment image is
created using an invoice template hierarchy where the root template type is
**Adjustment Image**.  The root template for an adjustment is determined by
the invoice format of the adjustment.

During production of an image, the tree of nested templates, rooted at the
root template, is evaluated depth-first.

Data for images can be generated using a number of invoice formats.  The
allowable formats are configurable and are defined by the reference codes of
the **OUTPUT_IMAGE_TYPE** reference type.  Invoice formats have an output
image type.  Each output image type has a file extension (e.g. txt, xml, TeX,
TeX.Z, TeX.gz). Based on that file extension the IGP may compress the invoice
image before storing the image in the database.

The treigp may be configured in either single-process or multi-process mode by
specifying the maximum number of child processes.

In single-process mode, the treigp server process is the only process that is
instantiated.

In multi-process mode, the treigp server forks and execs up to the
MAX_CHILD_PROCESSES number of IGP child processes as required. The interface
between the parent treigp process and the child IGP processes is via unnamed
duplex pipes.  The parent process delegates the generation of images to its
child processes.

The treigp_tran process supports single process mode only.

[Contents]

* * *

## Configuration

A parameter that identifies the configuration to use for the IGP instance is
passed to IGP servers on the command line (see ubbconfig file).  This
parameter may either be a configuration name or the sequence number of an IGP
configuration.

Multiple instances of IGP server may use the same configuration.

The following configuration attributes exist in the database for a
configuration item type of IGP:

**MAX_CHILD_PROCESSES** (Optional)

    This attribute is used by the treigp only.  It specifies the number of child processes the IGP will spawn.  For example, a value of 2 means run with one parent process and two child processes, a value of 1 means one parent process and one child process and a value of 0 means run in single process mode .  When more than one process is specified, the parent does not process requests but simply sends to the child processes requests to be processed.   This attribute is optional.  If it is not present the IGP runs as if a zero value was specified (i.e. in single process mode).  
If multi-tenancy is in use, the effective tenant is not propagated to child
processes and therefore child processes will not run with an effective tenant.
For this reason, if multi-tenancy is enabled, the IGP should be configured not
to use child processes, as the child processes will not be able to correctly
retrieve tenanted configuration.



**BUILD_DIR** (Mandatory)

    The directory to use for temporary data files.


**KEEP_BUILD_FILES **(Optional)

    This boolean flag specifies whether temporary data files should be deleted when no longer required.  If FALSE then temporary files are deleted.  Note that setting KEEP_BUILD_FILES to TRUE will effectively disable the MEMORY_IMAGE_SIZE option, as files must be written to disk in order to keep them.  If no value is supplied for this attribute then a default value of FALSE is used.


**KEEP_WHITESPACE **(Optional)

    This boolean flag specifies whether whitespace should be removed for each generated line. If FALSE, any blank lines are removed, and whitespace (identified by the C isspace() function) is stripped from the start and end of each line. However, the characters that end the line are preserved. That is, if the original line ends with a carriage-return immediately followed by a line-feed then the stripped line ends with the same pair of characters. If the original line ends with only a line-feed then the stripped line also ends with only a line-feed. If no value is supplied for this attribute then a default value of FALSE is used.


**MEMORY_IMAGE_SIZE **(Optional)

    The maximum size (in bytes) of an invoice image that can processed entirely in memory. If specified as an integer with a trailing "M" (egg "10M"), then the size is considered to be in megabytes. When combined with "gz" compression (or no compression), this option removes the need for IGP to use temporary files.  If no value is supplied then a default value of 5M is used.  
If the size of an image exceeds this maximum value, a standard temporary file
(on disk) is created instead of processing the image in memory. Temporary
files are also created if KEEP_BUILD_FILES is TRUE or if a compression scheme
other than "gz" is used.  If no value is supplied for this attribute then a
default value of 5 megabytes is used.



**DEBUG_LEVEL` `**(Optional)

    Specifies the level of debugging information.  The default debug level is 0 (no debug).

Decimal | Mnemonics | Description  
---|---|---  
0 |  OFF  | All tracing off (default)  
1 | ORA | Turn on Oracle SQL tracing.  
2 | SQL or RDB | Turn on SQL connection tracing as well as Database tracing within the IGP.  
4 | INV | Invoice values  
8 | TMP | Template values  
16 | CMD | Command values  
32 | CMS | Compress node variable values  
64 | EPM | Turn on EPM debug  
128 | MSG | Message variable values  
256 | CHD | Child process information  
512 | MEM | Print memory report on completion.  
1024 | EPM_LIGHT | Turn on EPM debug without function parameter values  or return values  
1023 | ALL | All of the above (except EPM_LIGHT)  
  
    Multiple debug levels can be set as shown in the following example: 

` ecp biTrcIGP&('513') - Sets level 512 + level 1  
ecp biTrcIGP&('ORA,MEM') - Sets ORA(1) and MEM(512)`

    Note: SQL and RDB have identical behaviour i.e. they turn on both SQL connection tracing and Database tracing. 
    This behaviour was chosen in order to be backwards compatible with v9 (and older) where only the SQL mnemonic is supported, but SQL trace also includes RDB trace.


**VIEW_CACHE_SIZE` `** (Optional)

    The size of the cache of template views. If specified as a positive number the cache's size is the number of views that can be stored.  If specified as a number with a trailing "M" (e.g. "100M") then the cache's size is the number of megabytes that the cache is able to consume. A cached template view contains the result rows that are returned for a given set of parameters bound to the template view query. See the Caching section for more detail.  Template views will not be cached if no size or a zero size is specified.


**VIEW_CACHE_ITEM_SIZE** (Optional)

    Only applicable if a VIEW_CACHE_SIZE greater than zero has been specified, this specifies the maximum size (in bytes) of any single item in the template view cache.  If specified as an integer with a trailing "M" (e.g. "10M"), then the size is considered to be in megabytes. If the template view cache item grows to exceed this size, the cache item is removed from the cache. See the Caching section for details.  Defaults to 25% of the size of VIEW_CACHE_SIZE if no size or a zero size is specified.


**GLOBAL_DA_CACHE_SIZE` `**(Optional)

    The size of the cache of derived attributes with a storage context of global. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" (e.g. "100M") then the cache's size is the number of mega bytes that the cache is able to consume.  If not specified, the global derived attribute cache has an unlimited size.


**NON_GLOBAL_DA_CACHE_SIZE` `**(Optional)

    The size of the cache of derived attributes with a storage context of non-global. If specified as a positive number the cache's size is the number of derived attributes that can be stored. If specified as a number with a trailing "M" (e.g. "100M") then the cache's size is the number of megabytes that the cache is able to consume.  If not specified, the non-global derived attribute cache has an unlimited size.


**ERROR_THRESHOLD **(Optional)

    If the value of this attribute is not zero then: 
       * AdjustmentImageGenerate& aborts if the number of adjustments for which images failed to be generated equals or exceeds this value; and
       * InvoiceImageGenerate& aborts if the number of root customers for which invoice images failed to be generated equals or exceeds this value.

If no value is supplied for this attribute then a default value of 1 is used.



**STATISTICS_TIMEOUT**(Optional)

    Specifies how frequently the IGP and its associated child processes log their statistics in the TRE Monitor while the treigp is active. This value is the integer number of seconds between each successive call to STATISTICS_FUNCTION while the treigp is running. STATISTICS_FUNCTION is also called on commencement and completion of each new Tuxedo request. If not specified, statistics are not generated.
     
**STATISTICS_FUNCTION** (Optional)

    Specifies the function that is called every STATISTICS_TIMEOUT seconds while the treigp is active. The default STATISTICS_FUNCTION  is IGPLogStatistics&(). 

If any of the above attributes marked as mandatory are not present, the IGP
server will fail to boot.

[Contents]

* * *

## Service biIGP

**Description**

Contains all of the functions to generate invoices and reports. The functions
currently implemented for this service are:

       * biAdjustmentImageGenerate&
       * biAdjustmentImageGenerate& (2)
       * biInvoiceImageGenerate&
       * biInvoiceImageReGenerate&
       * biReportImageGenerate&

[Contents]

* * *

### biAdjustmentImageGenerate&

**Syntax**

> biAdjustmentImageGenerate&(
>

>> > AdjustmentIdList&[],  
>  var SuccessAdjustmentIdList&[],  
>  var ErrorAdjustmentIdList&[],  
>  var ErrorMessageIdList&[],  
>  var ErrorMessageList$[])

**Parameters**

Identical to AdjustmentImageGenerate&.

**Description**

This function is a remote wrapper around  AdjustmentImageGenerate&.

**Returns**

The result of calling AdjustmentImageGenerate&.

[Contents]

* * *

### biAdjustmentImageGenerate& (2)

**Syntax**

> biAdjustmentImageGenerate&(AdjustmentId&)

**Parameters**

Identical to AdjustmentImageGenerate& (2).

**Description**

This function is a remote wrapper around  AdjustmentImageGenerate& (2).

**Returns**

The result of calling  AdjustmentImageGenerate& (2).

[Contents]

* * *

### biInvoiceImageGenerate&

**Syntax**

> biInvoiceImageGenerate&(

> > BillRunId&,  
>  EffectiveDate~,  
>  BillRunOperationId&,  
>  RootCustomerNodeList&[],  
>  var SuccessCustomerNodeList&[],  
>  var ErrorCustomerNodeList&[],  
>  var SuppressedCustomerNodeList&[],  
>  var Statistics?{}
>
> )
>
> biInvoiceImageGenerateCorporate&(  
>  
>          BillRunId&,  
>          EffectiveDate~,  
>          BillRunOperationId&,  
>          RootCustomerNodeList&[],  
>          var SuccessCustomerNodeList&[],  
>          var ErrorCustomerNodeList&[],  
>          var SuppressedCustomerNodeList&[],  
>          var Statistics?{}  
>  
>  )  
>  
>  

**Parameters**

Identical to InvoiceImageGenerate&.

**Description**

This function is a remote wrapper around  InvoiceImageGenerate&.

biInvoiceImageGenerateCorporate& is another wrapper around
InvoiceImageGenerate& which  can be used for Corporate Customers. The only
difference is in the remote service name,  biIGPCorporate being used in
biInvoiceImageGenerateCorporate&.  This to  allow Corporate customers to be
directed to their own set of igp servers  which may have a different
configuration more suited to the processing of large Corporate hierarchies.

**Returns**

The result of calling InvoiceImageGenerate&.

[Contents]

* * *

### biInvoiceImageReGenerate&

**Syntax**

> biInvoiceImageReGenerate&(
>

>> InvoiceId&,  
>  SeqNr&
>
> )

**Parameters**

Identical to InvoiceImageReGenerate&.

**Description**

This function is a remote wrapper around InvoiceImageReGenerate&.

**Returns**

The result of calling InvoiceImageReGenerate&.

[Contents]

* * *

### biReportImageGenerate&

**Syntax**

> biReportImageGenerate&(
>

>> TaskId&,  
>  EffectiveDate~,  
>  TempDataId&,  
>  TemplateId&,  
>  var Statistics?{}
>
> )

**Parameters**

Identical to ReportImageGenerate&.

**Description**

This function is a remote wrapper around ReportImageGenerate&.

**Returns**

The result of calling ReportImageGenerate&.

[Contents]

* * *

## Service biIGPTran

**Description**

Contains all of the functions to generate documents on the transactional
server (treigp_tran). The functions currently implemented for this service
are:

       * [bi]DocumentImageGenerate@
       * [bi]DocumentImageInsert&
       * [bi]DocumentImageFetchById&
       * [bi]DocumentImageUpdate&
       * [bi]DocumentImageDelete&

[Contents]

* * *

### [bi]DocumentImageGenerate@

**Syntax**

> [bi]DocumentImageGenerate@(TemplateId&, const DocumentParameters?{})

**Parameters**

TemplateId& | ID of the template used to generate the document.  
---|---  
const DocumentParameters?{} | A hash of parameters to be merged into the template.  
  
**Description**

This function produces a document image by merging the field values given in
the DocumentParameters?{} parameter into the template identified by
TemplateId&.

The TemplateId& must correspond to a TEMPLATE_HISTORY record that has context
'Document' and a TEMPLATE_TYPE_CODE of either 'Document Image' or 'Microsoft
Word 2007 XML Document Image'.

**Implementation**

The "bi" version of this function (i.e. biDocumentImageGenerate) is provided
as a wrapper around the DocumentImageGenerate@ function, evaluating in the
biIGPTran service.

The DocumentImageGenerate@ function is implemented as a built-in function as
follows:

      1. The DocumentParameters?{} hash is copied to the Document?{} global direct variable.  The Document?{} direct variable is available for use in standard IGP template expressions.
      2. If the template type code is Document Image then standard image generation is performed.
      3. If the template type code is Microsoft Word 2007 XML Document Image then the template is a zip file:
        1. The template blob is extracted from the WORD_IGP_TEMPLATE column of the  TEMPLATE_HISTORY.
        2. The extracted template is unzipped into a working directory tree in the build area.
        3. Each xml file in the directory tree is read into memory and standard igp template processing is performed with the output written to a replica directory tree.
        4. All files in the replica tree are zipped and the resultant file is read into memory and returned as the blob result of the function. 

The zip and unzip utilities are required to produce a Word 2007 document from
its template.

**Returns**

If successful returns the generated document image as a blob and raises an
exception otherwise.

[Contents]

* * *

### [bi]DocumentImageInsert&

**Syntax**

> [bi]DocumentImageInsert&(var LastModified~, FieldNames$[],FieldValues?[])

**Parameters**

var LastModified~ | Gets set to the last modified date of the inserted document image record  
---|---  
FieldNames$[] | The names of the  DOCUMENT_IMAGE_TRE_V columns which are to be given values.  See the Description section for details.  
FieldValues?[] | Values of fields in the order they were specified in FieldNames$[].  
  
**Description**

This function is called to store a document image in the DOCUMENT_IMAGE table.
It can be called to either store an existing document image or to generate and
then store a document image.

When called to store an already generated image the DOCUMENT_CONTENTS column
must be specified and the corresponding value must be a blob containing the
document image.  When called to also generate the image to be stored, the
pseudo column DOCUMENT_PARAMETERS must be specified and the corresponding
value must be a hash of the document parameters required for the call to
DocumentImageGenerate@..

An exception is raised if both the DOCUMENT_CONTENTS and the
DOCUMENT_PARAMETERS columns have been specified.

The TEMPLATE_ID column must be specified and correspond to a template of type
of "Document Image" or "Microsoft Word 2007 XML Document Image".

If either the REFERENCE_ENTITY_TYPE  or REFERENCE_ENTITY_ID have been
specified then both REFERENCE_ENTITY_TYPE and REFERENCE_ENTITY_ID must be
specified.

The following columns are derived and an exception is raised if any are
specified in the FieldNames$[] parameter:

       * STORED_IMAGE_TYPE
       * STORED_IMAGE_TYPE_CODE 
       * OPERATOR_ID
       * LAST_MODIFIED

All other columns are optional.

If DOCUMENT_IMAGE_ID is not specified and an ID column has been specified
(i.e. any of CUSTOMER_NODE_ID, PERSON_ID, CONTRACT_ID or QUERY_ID) the
customer partition  is derived from the ID column value and used to determine
the next unique value for DOCUMENT_IMAGE_ID.  

If DOCUMENT_IMAGE_ID is not specified and no ID columns are specified the
default partition for the instance is used to determine the next unique value
for DOCUMENT_IMAGE_ID.

**Implementation**

The "bi" version of this function (i.e. biDocumentImageInsert&) is provided as
a wrapper around the DocumentImageInsert& function, evaluating in a biIGPTran
service.

The DocumentImageInsert& is implemented in EPM as follows:

      1. Field names and values are validated.
      2. Values are derived for columns that are not specified but require values.
      3. If the document needs to be generated DocumentImageGenerate@ is called.
      4. A record is inserted into the DOCUMENT_IMAGE  table.

**Returns**

ID of inserted image.  Raises an exception otherwise.

[Contents]

* * *

### [bi]DocumentImageFetchById&

**Syntax**

> [bi]DocumentImageFetchById&(DocumentImageId&, const FieldNames$[],
> FieldValues?[])

**Parameters**

DocumentImageId& | Unique identifier of the document image for which the fetch is required.  
---|---  
const FieldNames$[] | The names of the  DOCUMENT_IMAGE_TRE_V columns that are to be retrieved.  
FieldValues?[] | Values of fields in the order they were specified in FieldNames$[].  
  
**Description**

This function retrieves values for the specified columns in the
DOCUMENT_IMAGE_TRE_V view for the specified document identifier.

**Implementation**

The "bi" version of this function (i.e. biDocumentImageFetchById&) is provided
as a wrapper around the DocumentImageFetchById& function, evaluating in a
biIGPTran service.

**Returns**

Returns 1 if successful and raises an exception otherwise.

[Contents]

* * *

### [bi]DocumentImageUpdate&

**Syntax**

> [bi]DocumentImageUpdate&(DocumentImageId&, var LastModified~, FieldNames$[],
> FieldValues?[])

**Parameters**

DocumentImageId& | Unique identifier of the document image to be updated.  
---|---  
var LastModified~ | On entry a check is performed to ensure that the LastModified~ matches the LAST_MODIFIED value in the DOCUMENT_IMAGE table for the given document ID.  
On exit  LastModified~ is set to the LAST_MODIFIED of the updated
DOCUMENT_IMAGE record.  
FieldNames$[] | The names of the  DOCUMENT_IMAGE_TRE_V columns which are to be given values.  See the Description section for details.  
FieldValues?[] | Values of fields in the order they were specified in FieldNames$[].  
  
**Description**

This function is called to update a record in the DOCUMENT_IMAGE table.

A new image may be generated by specifying the TEMPLATE_ID column and the
pseudo column DOCUMENT_PARAMETERS.  The corresponding value for the
DOCUMENT_PARAMETERS column must be a hash of the document parameters needed to
call DocumentImageGenerate@.   The TEMPLATE_ID column must correspond to a
template of type of "Document Image" or "Microsoft Word 2007 XML Document
Image".

An exception is raised if both the DOCUMENT_CONTENTS and the
DOCUMENT_PARAMETERS columns have been specified.

If either the REFERENCE_ENTITY_TYPE  or REFERENCE_ENTITY_ID have been
specified then both REFERENCE_ENTITY_TYPE and REFERENCE_ENTITY_ID must be
specified.

The following columns are derived or not updateable.  An exception is raised
if any are specified in the FieldNames$[] parameter:

       * DOCUMENT_IMAGE_ID 
       * STORED_IMAGE_TYPE
       * STORED_IMAGE_TYPE_CODE 
       * OPERATOR_ID
       * LAST_MODIFIED

**Implementation**

The "bi" version of this function (i.e. biDocumentImageUpdate&) is provided as
a wrapper around the DocumentImageUpdate& function, evaluating in a biIGPTran
service.

The DocumentImageUpdate& is implemented in EPM as follows:

      1. Field names and values are validated.
      2. If the document needs to be generated DocumentImageGenerate@ is called.
      3. The DOCUMENT_IMAGE table is updated.

**Returns**

1 on success and raises an exception otherwise.

[Contents]

* * *

### [bi]DocumentImageDelete&

**Syntax**

> [bi]DocumentImageDelete&(DocumentImageId&)

**Parameters**

DocumentImageId& | Unique identifier of the document to be deleted.  
---|---  
  
**Description**

This function deletes an existing DOCUMENT_IMAGE record.

**Implementation**

The "bi" version of this function (i.e. biDocumentImageDelete&) is provided as
a wrapper around the DocumentImageDelete& function, evaluating in a biIGPTran
service.

**Returns**

1 if successful and raises an exception otherwise.

[Contents]

* * *

### Event biPurge

**Description**

Purges various entities cached by the IGP parent process and its children.

[Contents]

* * *

## EPM Interface

These functions provide an EPM interface to the IGP. The descriptions have
been split into the following sections for convenience:

       * IGP Functions
       * Purge/Trace Functions
       * Template Processing Functions

[Contents]

* * *

## IGP Functions

These functions are designed to be called remotely via the TRE. Currently they
consist of:

       * AdjustmentImageGenerate&
       * AdjustmentImageGenerate& (2)
       * InvoiceImageGenerate&
       * InvoiceImageReGenerate&
       * ReportImageGenerate&



[Contents]

* * *

### AdjustmentImageGenerate&

**Syntax**

> AdjustmentImageGenerate&(
>

>> > AdjustmentIdList&[],  
>  var SuccessAdjustmentIdList&[],  
>  var ErrorAdjustmentIdList&[],  
>  var ErrorMessageIdList&[],  
>  var ErrorMessageList$[])

**Parameters**

AdjustmentIdList&[] | Array of IDs of adjustments for which images are to be generated.  
---|---  
SuccessAdjustmentIdList&[] | Array of IDs of adjustments for which images were successfully generated.  
ErrorAdjustmentIdList&[] | Array of IDs of adjustments for which images failed to be generated.  
ErrorMessageIdList&[] | Array of IDs of error messages, one ID for each failed adjustment.  
ErrorMessageList$[] | Array of error messages, one error message for each failed adjustment.  
  
**Description**

This function generates adjustment images and stores the images in the
ADJUSTMENT table.

Each adjustment image is generated in the order in which its ID was specified
in the AdjustmentId&[] parameter.  Duplicate adjustment IDs in the parameter
are silently ignored.

The template for each invoice format for each adjustment must be of type
**Adjustment Image** and must be of context **CustomerNode** , and this
template must reference a database view that includes an ADJUSTMENT_ID column
(such as  INV_CUSTOMER_ADJUSTMENT_V).  The generation of the adjustment image
fails with an error if these conditions are not met.

On successful generation of an image for an adjustment, the ID of the
adjustment is appended to the SuccessAdjustmentIdList&[] parameter.  If an
image cannot be generated for an adjustment then the ID of the adjustment, the
ID of the error that occurred, and the text of the explanatory message are
appended to the ErrorAdjustmentIdList&[], ErrorMessageIdList&[] and
ErrorMessageList$[] parameters, respectively.

On successful generation of an image for an adjustment this function sets the
values of the PENDING_GENERATION_IND_CODE and PRINTED_IND_CODE columns for the
adjustment to NULL and sets the value of the IMAGE_GENERATED_IND_CODE column
to 1.

**Returns**

1 on success, 0 on failure.  Failure results if the number of adjustments for
which images could not be generated equals or exceeds the value of
ERROR_THRESHOLD.  On failure, some adjustment images may have been
successfully generated; these images are retained in the ADJUSTMENT table.

On a fatal error this function logs an error message and raises an exception
that indicates the reason for the error.

[Contents]

* * *

### AdjustmentImageGenerate& (2)

**Syntax**

> AdjustmentImageGenerate&(AdjustmentId&)

**Parameters**

AdjustmentId& | ID of adjustment for which an image is to be generated.  
---|---  
  
**Description**

This function is a wrapper around  AdjustmentImageGenerate&.  It passes
AdjustmentId& to AdjustmentImageGenerate&() and raises an exception if the
output parameters from AdjustmentImageGenerate&[] indicate that an error
occurred.

**Returns**

1 if an image was successfully generated for the adjustment. An exception is
raised otherwise.

[Contents]

* * *

### InvoiceImageGenerate&

**Syntax**

> > InvoiceImageGenerate&(
>

>> > BillRunId&,  
>  EffectiveDate~,  
>  BillRunOperationId&,  
>  RootCustomerNodeList&[],  
>  var SuccessCustomerNodeList&[],  
>  var ErrorCustomerNodeList&[],  
>  var SuppressedCustomerNodeList&[],  
>  var Statistics?{})

**Parameters**

BillRunId& | ID of the bill run.  
---|---  
EffectiveDate~ | Effective date to use for accessing date ranged items.  
BillRunOperationId& | ID of the bill run operation.  
RootCustomerNodeList&[] | A list of the IDs of one or more root customers.  
var SuccessCustomerNodeList&[] | A list of the IDs of any successfully processed customers.  
var ErrorCustomerNodeList&[] | A list of the IDs of any customers who failed processing.  
var SuppressedCustomerNodeList&[] | Always returned empty. This function does not suppress customers.  
var Statistics?{} | A hash of processing statistics, including:  
_" Images": Number of Images Generated  
"Templates": Number of Templates Instantiated  
"ImageSize": Total Image Size (pre-compression) in Bytes  
"ImageSizeCompressed": Total Image Size (post-compression) in Bytes_  
  
**Description**

This function generates invoice images for all invoices identified by
BillRunId&, BillRunOperationId& and RootCustomerNodeList&[]. The
EffectiveDate~ is used for accessing any date ranged configuration items. The
lists of successfully processed and failed customers are returned in variable
parameters.

If any customer specified in RootCustomerNodeList&[] is not a root customer,
the function will fail.

Before commencing the generation of invoice images the following preliminary
operations are performed:

      1. For each customer in the RootCustomerNodeList&[]
        1. If the customer is not a root customer abort and document the reason for failure in log.out. 
        2. If the customer has no un-generated invoices at EffectiveDate~ 
          1. Insert a record into CUSTOMER_NODE_BILL_RUN table for the customer with a STATUS_CODE of 3 (Success)
          2. Add the customer to the SuccessCustomerNodeList&[].  No further processing is performed for that root customer or any of its children
        3. Otherwise attempt to lock the root customer by updating the CUSTOMER_NODE table with the BILL_RUN_ID and BILL_RUN_OPERATION_ID of the operation.  If either of these fields are already set and do not match the parameter values, it is assumed that the customer is locked by another process. In this case:
          1. Insert a record into CUSTOMER_NODE_BILL_RUN table for the customer with a STATUS_CODE of 4 (Failure) and an appropriate error message. 
          2. Add the customer to the ErrorCustomerNodeList&[].  No further processing is performed for that root customer or any of its child customer nodes.  

      2. A database commit is performed.
      3. The view cache (used if VIEW_CACHE_SIZE > 0) is cleared.

After each invoice image is generated the following administrative operations
are performed:

      1. For each root customer:
        1. If not all invoices were processed for the customer
          1. Update the CUSTOMER_NODE_BILL_RUN table for the customer, set STATUS_CODE to 4 (Failure), END_DATE to the current time and set the error details appropriately.
          2. Clear the BILL_RUN_ID and BILL_RUN_OPERATION_ID columns in the CUSTOMER_NODE table to unlock the root customer. 
          3. Add the customer to ErrorCustomerNodeList&[].
        2. Otherwise:
          1. Add the customer to either SuccessCustomerNodeList&[] or ErrorCustomerNodeList&[] depending on the result of invoice image generation for that customer. Customers that have had some or all of their invoice images suppressed are still treated as successful since their invoices may have non-zero balances which need to be processed by subsequent bill run steps.
      2. A database commit is performed.

**Returns**

1 on success, 0 on failure. Failure results if the number of root customers in
error is not less than the value of ERROR_THRESHOLD.

On a fatal error this function logs an error message and raises an exception
that indicates the reason for the error.

[Contents]

* * *

### InvoiceImageReGenerate&

**Syntax**

> InvoiceImageReGenerate&(
>

>> InvoiceId&,  
>  SeqNr&
>
> )

**Parameters**

InvoiceId& | ID of an invoice.  
---|---  
SeqNr& | Sequence number of a particular invoice image to be regenerated. If 0, all invoice images for the InvoiceId& are regenerated.  
  
**Description**

This function (re)generates invoice images, given an Invoice ID and optional
Seq Nr.

The generated images are stored in the INVOICE_CONTENTS table.

**Returns**

1 on success, 0 on failure.

[Contents]

* * *

### ReportImageGenerate&

**Syntax**

> ReportImageGenerate&(
>

>> TaskId&,  
>  EffectiveDate~,  
>  TempDataId&,  
>  TemplateId&,  
>  var Statistics?{}
>
> )

**Parameters**

TaskId& | ID of the task.  
---|---  
EffectiveDate~ | Effective date to use for accessing date ranged items.  
TempDataId& | ID used in selecting information on the reports to generate.  
TemplateId& | ID of the Invoice or Statement Image template.  
var Statistics?{} | A hash of processing statistics, including:  
_" Images": Number of Images Generated  
"Templates": Number of Templates Instantiated  
"ImageSize": Total Image Size (pre-compression) in Bytes  
"ImageSizeCompressed": Total Image Size (post-compression) in Bytes_  
  
**Description**

This function generates report images and stores the images in the
TASK_QUEUE_RESULT table.

**Returns**

1 on success, 0 on failure.

[Contents]

* * *

## Purge/Trace Functions

These functions are designed to be invoked remotely via biTrcInvoke service.
Currently they consist of:

       * biTrcIGP&
       * DerivedTablePurge&
       * FunctionPurge&
       * IGPTrace&
       * InvoiceMessagePurge&
       * ReferenceTypePurge&
       * ReferenceTypePurgeById&
       * ReferenceTypePurgeByLabel&
       * SubtotalPurge&
       * TariffPurge&
       * TemplatePurge&

[Contents]

* * *

### biTrcIGP&

**Syntax**

> biTrcIGP&(DebugLevel$)

**Parameters**

DebugLevel$ | The level of debug tracing required.  See the configuration item's debug level description for details on the levels.  
The level is the string mnemonic representation of the debug level.  
---|---  
  
**Description**

Sets the specified debug level for all treigp and treigp_tran servers running
on the current instance.

**Implementation**

biBroadcastFunctionCall&  is used to invoke the IGPTrace& function with the
specified DebugLevel$ within all treigp and treigp_tran servers on the current
instance.

[Contents]

* * *

### DerivedTablePurge&

**Syntax**

> DerivedTablePurge&(TableName$)

**Parameters**

TableName$ | The name of the Derived Attribute Table to purge.  
---|---  
  
**Description**

This callback function purges information for the specified Derived Attribute
Table from the DamTable caches, checking both the Global and Non-Global caches
(although any given Derived Attribute Table can only exist in one of these two
caches, which one isn't known at the time of purging).

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### FunctionPurge&

**Syntax**

> FunctionPurge&(FunctionName$)

**Parameters**

FunctionName$ | The name of the function to purge.  
---|---  
  
**Description**

This callback function purges information for the specified function from the
IGP's BuiltInSQLFunctionParser.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### IGPTrace&

**Syntax**

> IGPTrace&(DebugLevel$)

**Parameters**

DebugLevel$ | Diagnostic debug level   
---|---  
  
**Description**

This function sets the diagnostic debug level for this IGP to the level
specified by DebugLevel$. This value is interpreted in the same manner as the
`<debug level>` configuration attribute.  
Debug information requests are propagated to the client child processes via
the IPC pipes and each child takes the same action as the parent upon
receiving the message.  


Setting a new trace level turns off any existing trace levels. Multiple trace
levels can be set as shown in the following example:

` ecp biTrcIGP&('513') - Sets level 512 + level 1  
ecp biTrcIGP&('ORA,MEM') - Sets ORA(1) and MEM(512) `

**Implementation**

This function is implemented as a built-in function.  It is registered by the
IGP.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### InvoiceMessagePurge&

**Syntax**

> InvoiceMessagePurge&(InvoiceMessageId&)

**Parameters**

InvoiceMessageId& | The Id the Invoice Message to purge.  
---|---  
  
**Description**

This callback function purges information for the specified Invoice Message
from the IGP's internal cache of Invoice Messages.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### ReferenceTypePurge&

**Syntax**

> ReferenceTypePurge&(ReferenceTypeAbbreviation$)

**Parameters**

ReferenceTypeAbbreviation$ | The abbreviation of the Reference Type to purge.  
---|---  
  
**Description**

This callback function purges information from IGP's internal
ReferenceTypeCache, as specified by the Reference Type abbreviation's.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### ReferenceTypePurgeById&

**Syntax**

> ReferenceTypePurgeById&(ReferenceTypeId&)

**Parameters**

ReferenceTypeId& | The Id of the Reference Type to purge.  
---|---  
  
**Description**

This callback function purges information for the specified Reference Type
from the IGP's internal ReferenceTypeCache.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### ReferenceTypePurgeByLabel&

**Syntax**

> ReferenceTypePurgeByLabel&(TypeLabel$)

**Parameters**

TypeLabel$ | The label of the Reference Type to purge.  
---|---  
  
**Description**

This callback function purges information from IGP's internal
ReferenceTypeCache, as specified by the Reference Type's label.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### SubtotalPurge&

**Syntax**

> SubtotalPurge&(SubtotalId&)

**Parameters**

SubtotalId& | The Id of the Subtotal to purge.  
---|---  
  
**Description**

This callback function purges information for the specified Subtotal from the
IGP's internal Subtotal cache.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### TariffPurge&

**Syntax**

> TariffPurge&(TariffId&)

**Parameters**

TariffId& | The Id of the Tariff to purge.  
---|---  
  
**Description**

This callback function purges information for the specified Subtotal from the
IGP's internal Tariff cache.

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

### TemplatePurge&

**Syntax**

> TemplatePurge&(TemplateId&)

**Parameters**

TemplateId& | The Id of the Template to purge.  
---|---  
  
**Description**

This callback function purges information for the specified template from the
IGP's internal Template cache

**Returns**

TRUE. Errors logged as appropriate.

[Contents]

* * *

## Template Processing Functions

These functions are designed to be called from within template expressions.
Currently they consist of:

       * InvoiceAccountPartitionNr&
       * InvoiceImageSuppress&
       * [bi]InvoiceReportAccounts&
       * TemplateCall&
       * TemplatePrint&

[Contents]

* * *

### InvoiceAccountPartitionNr&

**Syntax**

> > InvoiceAccountPartitionNr&()

**Parameters**

None.

**Description**

This function can be used in template processing to return the PARTITION_NR
associated with the ACCOUNT of the current invoice.  If customer partitioning
is not configured, the function will always return 1.

For example, the following could be included in the where clause of a template
which accesses the CHARGE table:

        
                        AND PARTITION_NR = /+InvoiceAccountPartitionNr&()+/

**Returns**

The PARTITION_NR associated with the ACCOUNT of the current invoice.  If
customer partitioning is not configured, the function will always return 1.

[Contents]

* * *

### InvoiceImageSuppress&

**Syntax**

> InvoiceImageSuppress&()

**Parameters**

None.

**Description**

If not called via biInvoiceImageRegenerate& then the current invoice is
suppressed.   This is achieved by raising an error, aborting EPM processing,
which is subsequently trapped by the IGP.  If called via
biInvoiceImageRegenerate& then the image should not be suppressed.

**Returns**

0 if called via biInvoiceImageRegenerate&, otherwise an error is raised.

[Contents]

* * *

### [bi]InvoiceReportAccounts&

**Declaration**

        
                [bi]InvoiceReportAccounts&(BillRunId&,
                                   EffectiveDate~,
                                   CustomerNodeId&,
                                   InvoiceSeqnr&,
                                   ExcludeInvoiceNodes&,
                                   ExcludeStatementNodes&,
                                   StopAtInvoiceNodes&,
                                   StopAtStatementNodes&,
                                   Depth&,
                                   IncludeSelf&) 

**Parameters**

BillRunId& | Bill run for which records will be generated.  
---|---  
EffectiveDate~ | Effective date of bill run.  
CustomerNodeId& | Customer Node for which to generate records.  
InvoiceSeqnr& | The invoice image sequence number for which to generate records.  
ExcludeInvoiceNodes& | If defined and non-zero, will exclude invoice nodes and below.  
ExcludeStatementNodes& | If defined and non-zero, will exclude statement (and Transferred Statement) nodes and below.  
StopAtInvoiceNodes& | If defined and non-zero, will include invoice nodes but exclude their children.  
StopAtStatementNodes& | If defined and non-zero, will include statement (or Transferred Statement) nodes but exclude their children.  
Depth& | Maximum Depth to search for children (<= 0 implies infinite).  
IncludeSelf& | If defined and non-zero, will include current node as SEQNR 0 in INV_REPORT_ACCOUNTS_T table.   
  
**Returns**

Returns number of rows inserted into the INV_REPORT_ACCOUNTS_T table.

**Description**

Populates the INV_REPORT_ACCOUNTS_T table with all accounts that have
contributed to statements or invoices for `CustomerNodeId&` and bill run
`BillRunId&`. This includes child accounts as well as _Transferred Statement_
accounts that transfer their statements to the customer being processed. Some
accounts may be filtered out according to input parameters.

This function is called from an invoice template prior to processing an _Other
Invoices_ template with a view name of INV_OTHER_INVOICES_V.

**Implementation**

The InvoiceReportAccounts& function is  implemented as local EPM, designed to
be run within the IGP. A "bi" version of this function (i.e.
biInvoiceReportAccounts&) is provided as a wrapper around the
InvoiceReportAccounts& EPM function, evaluating in a biFnEvaluateRW service.

[Contents]

* * *

### TemplateCall&

**Syntax**

> TemplateCall&(const TemplateName$)

**Parameters**

const TemplateName$ | The name of the template to process  
---|---  
  
**Description**

This function can be used in template expressions to process the template with
the specified name. It is equivalent to processing of a /-<template_name>-/
tag for the specified template name. This function would typically be used in
cases where it is necessary to loop under the control of EPM code rather than
based on the number of rows returned from a view. For example:

> /*  
>    while (more_child_data&) {  
>      TemplatePrint&('<tag>' + CustNode$ + '</tag>');  
>      TemplateCall&('MY_CHILD_TEMPLATE');  
>    }  
>  */

It can also be used where the name of the template to invoke needs to be under
programmatic control.

**Returns**

It returns TRUE if the specified template was processed successfully. An
exception is raised and a message logged if the specified template does not
exist at the effective date of image generation or there is an error
instantiating the specified template.

[Contents]

* * *

### TemplatePrint&

**Syntax**

> TemplatePrint&(const Text$)

**Parameters**

const Text$ | The text to print to the invoice.  
---|---  
  
**Description**

This function can be used in template expressions to append the specified text
to the current invoice/report image. It is equivalent to processing of a
/+Text$+/ tag. This function would typically be used in conjunction with
TemplateCall&() in cases where it is necessary to loop under the control of
EPM code rather than based on the number of rows returned from a view.

**Returns**

TRUE. An exception is raised and a message logged if the text couldn't be
output to the current image.

[Contents]

* * *

### LoggerReload&

**Declaration**

LoggerReload&()

**Parameters**

None.

**Description**

This function is overridden in order to propagate the logger reload to child
processes. Otherwise, it provides the same functionality as  LoggerReload&(1).

**Return Value**  
  
1 on success. Raises an error otherwise.

[Contents]

* * *

## Invoice Image Generation

      1. The details of all invoices to be generated for the bill run and root customers are selected and stored in an ordered list. If no invoice images are to be generated, no further processing is performed.  Invoice details in the list are stored in descending order of:
        1. BILLING_PRIORITY
        2. ROOT_CUSTOMER_NODE_ID (CUSTOMER_NODE_ID if ROOT_CUSTOMER_NODE_ID)
        3. INVOICE_ID
        4. CUSTOMER_NODE_INVOICE_FORMAT.SEQNR
Note that images will not be generated for customers with a reporting level of
_No Reporting_. Images are only generated for customers with a reporting level
of _Invoice_ , _Statement_ and _Transferred Statement_.  

  

      2. All tariffs and subtotals with a context of Service, Customer Node or Customer and an application environment of Rating or Billing are loaded and direct variables registered with the expression parser.  

  

      3. All direct variables associated with the views in the table below are selected and registered with the expression parser. Also shown is the variable context and template type.   
  
Note that only those direct variables actually used by a template, an invoice
message or a function directly called by a template are registered.  If a
direct variable is required by a nested function, then that direct variable
must be silently evaluated in the template e.g. `/*InvChargeGeneral1$*/` will
silently evaluate the `InvChargeGeneral1$` direct variable without modifying
the generated image.  
  
Note also that if a customised view is used for a Template Type of 'Normalised
Events', the columns CHARGE, KEY_VALUE, SUBTOTAL_DATE, SUBTOTAL_NAME and
TARIFF_NAME must have a corresponding direct variable defined.

  View | Variable Context | Template Type  
---|---|---  
INV_INVOICE_V | Customer Node | Invoice or Statement Image  
INV_CUSTOMER_V | Customer | Customer  
INV_CUSTOMER_NODE_HISTORY_V | Customer Node | Customer Node  
INV_PAYMENT_V | Customer Node | Payments  
INV_SERVICE_HISTORY_V | Service | Services  
INV_ADJUSTMENT_V | Customer Node | Adjustments  
INV_INVOICE_MESSAGE_HISTORY_V | Customer Node | Invoice Messages  
INV_NORMALISED_EVENT_V | Normalised Events | Normalised Events  
INV_OTHER_INVOICES_V | Customer Node | Other Invoices  
  


      4. Each invoice image is then generated in order from the list.  If this is the first invoice to be generated for the root customer a record is inserted into the CUSTOMER_NODE_BILL_RUN table with a STATUS_CODE of 2 (Running) and START_DATE set to the current time.
  

      5. When the last invoice for a root customer has been processed the CUSTOMER_NODE_BILL_RUN table is updated as follows:
         * STATUS_CODE is set to
           * 4 (Failure) - If invoice generation failed for any customer in the hierarchy
           * 3 (Success) - If all invoice images in the customer hierarchy were generated successfully, which includes having some or all invoice images suppressed.

>        * END_DATE is set to the current date
>        * If STATUS_CODE is set to failure ERROR_MESSAGE_ID and ERROR_MESSAGE
> are set appropriately from the error details.
>
> The CUSTOMER_NODE table is then updated to unlock the root customer by
> clearing the BILL_RUN_ID and BILL_RUN_OPERATION_ID columns.

For each customer node invoice format the associated template must be of type
**Invoice or Statement Image** ; an error occurs if this is not the case.

If an invoice is to be suppressed then no image is stored into the
INVOICE_CONTENTS table for that invoice.

[Contents]

* * *

## Image Generation

The IGP (or its child process if in multi-process mode) performs the following
steps to generate an image:

      1. The IGP (or its child process) opens a temporary file to store the image data.
      2. Templates for the image are processed and the results are written to the temporary file.
      3. The temporary file is closed.
      4. The temporary file is then optionally compressed, depending on the extension of the file (e.g. .Z or .gz).
      5. If the image is for a  non-suppressed invoice or an adjustment, the contents of the temporary file are inserted into the relevant database table (INVOICE_CONTENTS for a non-suppressed invoice, ADJUSTMENT for an adjustment).  A database commit is then performed.

If MEMORY_IMAGE_SIZE > 0 then temporary files are maintained in memory until
the size of the file exceeds the MEMORY_IMAGE_SIZE, and then a disk file is
used.

### Multi Process Mode

In multi-process mode, images are generated by the child processes of the IGP.
The algorithm for performing multi-processing of invoice images is as follows:

> > _for each image to be generated do_
>>

>>> _search child process table for an available (idle) child process_

>>>

>>> _if an idle child process was found then_

>>>

>>>> _send image generation request to this child process_

>>>>

>>>> _update child process table to indicate this child process is busy_

>>>

>>> _else if the number of running child processes has not yet reached maximum
then_

>>>

>>>> _create new half-duplex unnamed pipe_

>>>

>>>> _start new child process_

>>>>

>>>> _add details of new child process and pipe to child process table_

>>>>

>>>> _send image generation request to this child process_

>>>>

>>>> _update child process table to indicate this child process is busy_

>>>

>>> _else_

>>>

>>>> _wait for a child process to become idle (complete processing an image)_

>>>>

>>>> _send image generation request to this child process_

>>>>

>>>> _update child process table to indicate this child process is busy_

>>>

>>> _end if_

>>>

>>> _check if a child process has become idle (do not block)_

>>>

>>> _if a child process has become idle then_

>>>

>>>> _update child process table to indicate that child process is idle_

>>>

>>> _end if_

>>

>> _end for_

>>

>> _wait for all child processes to become idle (all images generated)_

Once a child process has completed processing an image it sends its process
ID, processing result and optional error details to the IGP via the IGP
receiver pipe. The child process is now idle.

If the IGP detects that a child process has died, the details for that child
process are removed from the child process table.

[Contents]

* * *

## Template Processing

      1. The template and the associated pre- and post-eligibility expression lists are retrieved from an in-memory cache.  If the template does not exist in the cache then it is retrieved from the database and stored into the cache.  If the template has to be retrieved from the database:
        1. The pre and post-eligibility expression lists and the expressions embedded in the template are parsed 
        2. If the template has a view associated with it (compulsory for all template types except **Document Image** and **Microsoft Word 2007 XML Document Image**) an SQL query is constructed and used to create and prepare a database cursor associated with the template.  The default WHERE clause for the query is overruled by stating a WHERE clause for the template.    
  
Templates of type **Microsoft Word 2007 Document Image** will never have an
associated view.  This is enforced by a database constraint.  Templates of
type **Document Image** have no default where clause and therefore must have a
WHERE clause if there is a view associated with the template.  
  
The table below shows the columns names that appear in the default WHERE
clause to constrain the SQL query for each template type.  


Template Type | Columns That Appear In Default Where Clause  
---|---  
Adjustment Image | ADJUSTMENT_ID  
Adjustments | INVOICE_ID  
Customer | CUSTOMER_NODE_ID, BILL_RUN_ID  
Customer Node | CUSTOMER_NODE_ID, BILL_RUN_ID, , INVOICE_SEQNR   
Invoice or Statement Image | INVOICE_ID, BILL_RUN_ID, INVOICE_SEQNR  
Invoice Messages | INVOICE_MESSAGE_ID, EFFECTIVE_DATE  
Normalised Events | INVOICE_ID, SERVICE_ID, EFFECTIVE_DATE  
Other Invoices | PRIME_CUSTOMER_NODE_ID, BILL_RUN_ID  
Payments | INVOICE_ID  
Services | INVOICE_ID  
  
> In addition to the above columns, if customer-partitioning is being used and
> the view contains the PARTITION_NR column, the default WHERE clause will
> also restrict the query to a single customer-partition.  This is equivalent
> to adding the following to a template WHERE clause:
>  
>             >                     AND partition_nr =
> /+InvoiceAccountPartitionNr&()+/

> > Note that:
>>

>>        * With the exception of **Document Image** and **Microsoft Word 2007
Document Image** template types the default WHERE clause is used for the root
template and the root template should not have an optional WHERE clause
specified,

>>        * A template with a context of Service should have a view that
contains a column named SERVICE_ID.

>>        * A template of type **Invoice Messages** should have a view that
contains a column named INVOICE_MESSAGE_ID.

>>        * A template of type **Adjustment Image** should have a view that
contains a column named ADJUSTMENT_ID.

>>        * Parameters are specified within the WHERE clause as expressions
using the `/+ <expression> +/` syntax that is also used within template text.
The expression can only access direct variables from an ancestor template (as
well as tariffs and subtotals when generating invoice images).

      2. If an equivalent template is in the active template list: 
         * The template is evaluated exactly once using the current data in the expression parser 
      3. If there is no equivalent template in the active template list, for each row returned by the cursor (see Caching for detail on this point): 
         * Column values from the row are assigned to the associated expression parser variables 
         * The template is evaluated
      4. If in non-cache mode the cursor is closed. Processing of the parent template resumes. 

[Contents]

* * *

## Evaluating Templates

      1. Before a template is evaluated, the pre-eligibility expressions associated with the template are executed. If any of the pre-eligibility expressions evaluates to zero then the template is not evaluated.
      2. Once the template is found to be eligible it is parsed. As the template is parsed it is written to the temporary invoice image file. When a substitution symbol is encountered an action is performed and all the text between the symbol pair are replaced by the result of the action. The table below shows the substitution symbol pairs and their meanings.

Substitution Symbols | Action | Result  
---|---|---  
/+ _expression_ +/ | Evaluate the expression. | Result of expression  
/* _expression_ */ | Evaluate the expression. | None  
/- _template name_ -/ | Process the template. | Result of template zero or more times.  
/` _expression 1 expression2 ..._ `/ | Process the expressions and execute the command specified by the result of expression1 passing the remaining expression results as arguments. | Standard output generated by the command.  
/! _expression 1 expression2 ..._ !/ | Process the expressions and execute the command specified by the result of expression1 passing the remaining expression results as arguments. | None.  
  
      3. Once the template has been evaluated, the post-eligibility expressions associated with the template are executed. If any of the post eligibility expressions evaluates to zero then the invoice image data associated with the template being processed is truncated from the temporary invoice file, otherwise it remains unchanged. 

[Contents]

* * *

## Using Tariffs and Subtotals in Templates

When generating an invoice image, the values of tariffs and subtotals may be
used anywhere in the IGP where expressions are accepted.  This includes
Template substitution expressions, Template eligibility expressions and where
clauses.

**Notes for using tariffs and subtotals in templates:**

1\. The tariff or subtotal may be referenced from any context.  If the
template is of a lower (or same) context, then the tariff/subtotal will be
obtained using the Id of the context of the tariff/subtotal. For example, in a
template at the service context, the tariff ExampleTariff# is referenced.
ExampleTariff# resides at the Customer context.   The tariff's value, if it
has not already been retrieved, will be retrieved from the charge table using
the customer node id from the Customer context.

If the tariff/subtotal is of a lower context than the template, then the last
value the tariff/subtotal was assigned will be used.  If no value has been
assigned then the tariff/subtotal will be undefined.

2\. When using a keyed tariff or subtotal in templates of type Normalised
Event, be aware that there may be multiple charge records for the one tariff
or subtotal. This can cause a "growing" hash or array.  i.e. for the first
record from the normalised event/charge view, one array value is added, on the
next charge for the same normalised event, the next array element is added,
and so it appears as though the tariff is "growing".  This will not occur when
using keyed tariffs and subtotals in the Customer, Customer Node and Service
contexts.

3\. When a context's entity changes (e.g. the service id changes for the
service context), all tariffs and subtotals that had values for that context
are set to undefined.

**Implementation**

The IGP reads in all tariffs and subtotals for the effective date of the bill
run and groups them according to context. All of these tariff and subtotal
entities are then loaded into the parser with a call back function that is
triggered when the tariff/subtotal is referenced (note that the IGP loads
function stubs as defined in the TPM to stop the parser from raising an error
if the stubbed function is parsed).  The call back function, when triggered,
ascertains the context of the referenced tariff/subtotal and, if the
tariff/subtotal's context is the same or higher than the template's context,
the call back function loads the value of all entities for that context (the
tariff or subtotal's context), by querying the CHARGE table.

If the context of the tariff/subtotal is lower than the template's, then
nothing is loaded, and all parser values for that context remain as they were.

The rules for querying the charge table are as follows:

Customer  | All charges for the current invoice id and customer node id where the tariff/subtotal's id is in the list of tariffs/subtotals for the customer context. The service Id is NULL.  
---|---  
Customer Node  | All charges for the current invoice id and customer node id where the tariff/subtotal's id is in the list of tariffs/subtotals for the customer node context. The service Id is NULL  
Service  | All charges for the current invoice id and service id where the normalised event id is NULL.   
  
For the normalised event type templates, each row of the normalised event view
is read and the value is assigned to the parser. As noted above, for tariffs
and subtotals that produce multiple charges for the one normalised event, this
can cause a "growing" effect if the tariff/subtotal is being printed for each
row of the view.

When the normalised event Id changes, all of the tariffs and subtotals added
for the charge view are made undefined.

In order to speed up the undefining process, each time a variable is defined,
its index is placed in a list that is specific to the context.  When the main
identifier for the context changes, all variables with indexes in the list are
made undefined, and the list is cleared.

[Contents]

* * *

## Caching

### Template Caching

Templates are cached in a date ranged hash table. A template can be fetched
from the cache using a combination of ID and effective date/time.  Templates
can be purged from the cache by using the biTemplatePurge& function.

Caching of cursors associated with templates is used to increase performance.
This is achieved by reusing the returned results of equivalent cursors as
explained below. Thus time-expensive operations of querying the database are
performed less frequently.

SQLCache objects are used as the cursor in the implementation to achieve the
caching of results from the database. In non-caching mode SQLCursor objects
are used as the cursor.

Cache mode works in the following context of processing templates:

       * If there is no equivalent template in the active template list: 
         * The template is added to the active template list. 
         * If cache mode is off then the SQLCursor associated with the template is opened and used as the template's cursor. 
         * If cache mode is on: 
           * If an equivalent SQLCache exists in the cached query list then the results of that cursor are used as the template's cursor.
           * Otherwise: 
             * An SQLCache cursor is associated with the template, opened and added to the cached query list. 
             * If number of elements in the list of cached cursors is greater than the maximum allowed (VIEW_CACHE_SIZE exceeded) 
               * Remove those queries which no templates (in the active template list) reference.
             * If the number of result rows stored for the cached query exceeds the VIEW_CACHE_ITEM_SIZE, the cached query rows are freed and the cached query is marked for purging from the cache. The template no longer caches further result rows.

#### Template Equivalence

A template, t1, is equivalent to another template, t2, iff:

       * Types of both templates are the same 
       * Views of both templates are the same 
       * The where clause of t1 is null, or matches the where clause of t2 
       * The order by clause of t1 is null, or matches the order by clause of t2 

#### Query Equivalence

A query, q1, is equivalent to another query, q2, iff:

       * Types of both queries are the same 
       * Views of both queries are the same 
       * The where clause of q1 matches the where clause of q2 
       * The order by clause of q1 matches the order by clause of q2 
       * All variable values in the where clause are the same 

### Invoice Message Caching

Invoice messages are cached in a date ranged hash table. An invoice message
can be fetched from the cache using (invoice_message_id, effective_date) as
the key. Invoice messages can be purged from the cache on an
invoice_message_id basis by using the biInvoiceMessagePurge& function.

### Subtotal Caching

Subtotals are cached by using a "Sub" instance. During evaluation of the
SubtotalPurge& function the tariff cache and subtotal cache are cleared.
Tariffs and subtotals are then loaded into these caches as they are required
during servicing of an IGP request. Each required tariff/subtotal definition
is retrieved from the database as at the effective date/time of the request.

### Tariff Caching

Tariffs are cached by using a "Gtm" instance. During evaluation of the
TariffPurge& function the tariff cache and subtotal cache are cleared. Tariffs
and subtotals are then loaded into these caches as they are required during
servicing of an IGP request. Each required tariff/subtotal definition is
retrieved from the database as at the effective date/time of the request.

[Contents]

* * *

## Purging

Purge commands are sent to the IGP via biTrcInvoke events (the IGP subscribes
to this TRE event). biTrcInvoke events specify a function to be run in IGP's
parser, which for purges are EPM callback functions (e.g.
InvoiceMessagePurge&, SubtotalPurge&, etc). Purge commands received by a
Parent IGP process will be propagated to all Child IGP processes as well as
the Parent process purging itself.  
  
Entities that IGP server will purge, and their associated EPM Callback
functions, are:

**Entity Type** | **FunctionName**  
---|---  
Derived Attribute Table | DerivedTablePurge&  
Function | FunctionPurge&  
Invoice Message | InvoiceMessagePurge&  
Reference Type by abbreviation | ReferenceTypePurge&  
Reference Types by Id | ReferenceTypePurgeById&  
Reference Type by label | ReferenceTypePurgeByLabel&  
Subtotal | SubtotalPurge&  
Tariff | TariffPurge&  
Template | TemplatePurge&  
  
[Contents]

* * *

## Memory Images

The MEMORY_IMAGE_SIZE option can be used to enable in-memory build files for
image generation. The value of MEMORY_IMAGE_SIZE defines the maximum size of
the memory file. If the value of MEMORY_IMAGE_SIZE is set to 0, only standard
disk files are used. If an image exceeds the MEMORY_IMAGE_SIZE, the memory
file is written to disk and the disk file is used for the remainder of the
image. By using a "capped" memory file size, a single configuration can
support both small and extremely large images.

When used in conjunction with "gz" (or no) compression, memory files remove
the need to use temporary disk files and will reduce the I/O requirements of
the IGP. Because of this performance advantage, it is suggested that "gz"
compression be used in preference to "Z" compression.

[Contents]

* * *

## Dunning Letters

When generating dunning letter images for invoices, the top-level template
(TemplateId&) and the identifier used for record matching (TempDataId&) are
supplied as function parameters to ReportImageGenerate&. The specified
template and identifier are used for all output documents. The TempDataId&
identifies which rows from the DUNNING_T table, populated by the  Dunning
Letter Generation schedule type, are to be selected for processing. The
template type must be **Reporting View** , and any nested templates must be
the same type. The resulting image for each dunning letter is stored in the
TASK_QUEUE_RESULT table using a task queue id (TaskQueueId&) also supplied as
a function parameter. The stored image type is determined by the invoice
format retrieved from the template view e.g. INV_DUNNING_V.INVOICE_FORMAT_ID.

When using nested templates to generate a dunning letter, the templates should
contain a where clause to limit the number of rows returned. This is because
all of the templates are of the same type, **Reporting View** , where the
default limiting clause is through the **TEMP_DATA_ID**. This column
corresponds to the **TASK_QUEUE_ID** which requires a **SEQNR** to uniquely
identify it. Hence, **TEMP_DATA_ID** by itself is not a tight enough
constraint to restrict the number of rows returned. A suggested limiting where
clause would be to use the **SEQNR** , as done by the **TASK_QUEUE_ID**. Note
that this requires the view corresponding to the template to include the
**SEQNR** as one of its columns.

[Contents]

* * *

## Statistics

IGP statistics are gathered via the function IGPStats?{}().  This function
returns a hash of statistics for the process from which it was called.   If
the function is called in the parent process, the appropriate statistics are
returned (See function IGPStats?{}()).   Different statistics are returned if
the function is called in the child process.  

The statistics returned from this function are logged periodically in the TRE
Monitor while the treigp is active. Configuration attributes determine exactly
how this is done.   STATISTICS_TIMEOUT determines how often statistics are
logged.  The IGP keeps a record of the last time that statistics were logged.
In the main loop of the IGP, if STATISTICS_TIMEOUT seconds have elapsed since
the last time statistics were logged, the IGP calls a function to do so.  If
the IGP is running is multi process mode, it also sends a command to each
child process, telling them to call the same function and log their
statistics.

The exact function that is called by the IGP and child processes is specified
by STATISTICS_FUNCTION.  This function is configurable and defaults to
IgpLogStatistics&().

As of version 9.00, the IGP adds entries to the EPM call stack for each
template with a format of "Template: <TemplateName>".   Templates are added to
the call stack just prior to evaluating their pre-eligibility criteria and
they are removed from the call stack after their post-eligibility criteria is
evaluated (if any).   If epm statistics is enabled then the epm statistics
will hence include:

      1. The number of times each template was called
      2. The elapsed time spent evaluating each template.
      3. The net time spent evaluating each template.  The net time is equal to the elapsed time minus the time spent:
         * Evaluating other templates called from this template
         * Evaluating functions called from expressions in this template (including any functions called from pre- and post-eligibility expressions)
         * SQL calls performed by this template

Furthermore, if the gathering of epm call graph statistics is enabled, then
the resultant call graphs will show the template call hierarchy and this is
likely to clearly show which templates are the key performance bottlenecks and
whether it is the SQL being performed or the function calls being made within
these templates that is causing the problem.

[Contents]

### IGPStats?{}

**Declaration**

        
                IGPStats?{}()

**Returns**

Returns a hash structure containing statistics that the IGP has gathered since
boot time

**Description**

The statistics returned in the hash structure depend on the configuration of
the IGP.   If the function is called from the parent process, the returned
hash contains the following statistics:

**Key** | **Description**  
---|---  
ImagesGenerated | (Integer) Number of images generated by this process.  
ImagesSuppressed | (Integer) Number of invoice images suppressed by this process.  
ProcessingTime | (Real) Number of seconds spent processing requests.  This includes WaitTime.  
TemplateViewCache | (Hash) Statistics gathered from IGP's internal template view cache. This is only enabled when the VIEW_CACHE_SIZE is set. | MaxSize | (Integer) The maximum size, in bytes, of the cache. (See the value of VIEW_CACHE_SIZE)  
---|---  
SizeBytesMax | (Integer) The SizeBytes high water mark  
SizeItemsMax | (Integer) The SizeItems high water mark  
SizeBytes | (Integer) The current size, in bytes, of the cache  
SizeItems | (Integer) The number of items currently in the cache  
PurgeCounts | (Integer) The number of LRU items that have been purged in the cache.  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
Aborts | (Integer) The number of times an item has exceeded the VIEW_CACHE_ITEM_SIZE  
RequestsSent | (Integer) Number of requests sent to children.  
ResponsesReceived | (Integer) Number of responses received from children.  
WaitTime | (Real) Number of seconds spent waiting for responses from children.  
ProcessName | (String) Name of the IGP process that produced these statistics. This will be `treigp` for the parent process.  
  
RequestsSent, ResponsesReceived and WaitTime will all be zero if the IGP is
running in single process mode.

If called from the child process, a hash containing the following statistics
is returned:

**Key** | **Description**  
---|---  
ImagesGenerated | (Integer) Number of images generated by this process.  
ImagesSuppressed | (Integer) Number of invoice images suppressed by this process.  
ProcessingTime | (Real) Number of seconds spent processing requests.  
TemplateViewCache | (Hash) Statistics gathered from IGP's internal template view cache. This is only enable when VIEW_CACHE_SIZE is set. | MaxSize | (Integer) The maximum size, in bytes, of the cache. (See the value of VIEW_CACHE_SIZE)  
---|---  
SizeBytesMax | (Integer) The SizeBytes high water mark  
SizeItemsMax | (Integer) The SizeItems high water mark  
SizeBytes | (Integer) The current size, in bytes, of the cache  
SizeItems | (Integer) The number of items currently in the cache  
PurgeCounts | (Integer) The number of LRU items that have been purged in the cache.  
Hits | (Integer) The number of times a requested item has been in the cache  
Misses | (Integer) The number of times a requested item has not been in the cache  
Aborts | (Integer) The number of times an item has exceeded the VIEW_CACHE_ITEM_SIZE  
RequestsReceived | (Integer) Number of requests received from the parent process.  
ProcessName | (String) Name of the IGP process that produced these statistics. This will be `igp_child` for a child process.  
ParentProcessId | (Integer) Process identifier of this child process's parent process.  
  
**Implementation**

IGPStats::GetInstance() is called to get a pointer to the current process's
statistics (either IGPStatsParent or IGPStatsChild).  CollectStats() is then
called to retrieve a hash ParserResult containing the required statistics.
CollectStats() is overridden for both IGPStatsParent and IGPStatsChild, so a
call to this function will return the required statistics.

[Statistics] [Contents]

* * *

### IGPLogStatistics&

**Declaration**

        
                IGPLogStatistics&()

**Returns**

1 (TRUE) if the function executed correctly, 0 (FALSE) otherwise

**Description**

This function is called periodically from within the IGP to log statistics to
the TRE Monitor. It first enables EPM call graph statistics and TRE
statistics. It then compares the hash returned from the current IGPStats?{}()
call with the hash returned from the previous call.  If there are no
differences or the elapsed processing time is 0, the function returns and no
statistics are logged.  Otherwise function biTREServerMonitor&() is called to
log the statistics gathered by IGPStats?{}() in the TRE Monitor.

**Implementation**

This function is implemented in EPM code.  EPM and TRE statistics are enabled
by calls to stats_on() and treStatsOn&() respectively.  Inter-call state
information (such as the result of IGPStats?{}() call) is maintained by global
variable ProcessState?{}.

[Statistics] [Contents]

* * *

### Signals

On receipt of a SIGUSR1 signal by the IGP parent process or by one of its
child processes, the process dumps a memory report to the
`$ATA_DATA_SERVER_LOG` directory with the name `igp.<pid>.mem`.  If the file
doesn't exist, it is created, otherwise a memory dump is appended to the end
of the file

On receipt of a SIGINT, SIGPIPE or SIGTERM signal, an IGP child process
terminates.

The following signals are handled by the IGP parent process:

SIGPIPE

SIGCHLD

    Removes the child process details from the list stored in the parent and logs a warning message if the child process terminated abnormally. (Child process is later recreated by the parent process.)
SIGINT

SIGTERM

    If received during a bill run operation it is presumed that the signal has been sent for a bill run stop request.  In this case the IGP terminates all children by sending them a SIGTERM signal and then immediately returns from the bill run operation.  Otherwise shuts down any remaining child processes then terminates.
     
    Note:  A bill run stop request may be initiated while the IGP is completing a bill run operation.  In this case the SIGTERM may be received by the IGP just after it has completed the operation.  This will cause the IGP to terminate.

[Contents]

* * *

--------------------------------------------------
## Contents

    Description
    Related Documents
    Tables Maintained
    Tables Referenced
    Functions
    Bill Run Operation Statistics
    Bill Run Statistics
    Business Rules

* * *

## Description: TRE Billrun Services

The TRE Bill Run functions provide an interface for viewing and manipulating
bill runs and bill run operations in the system.

[Contents]

* * *

## Related Documents

       * Unit Test Plan for TRE Bill Run Functions

[Contents]

* * *

## Tables Maintained

       * BILL_RUN
       * BILL_RUN_TYPE
       * BILL_RUN_OPERATION
       * CUSTOMER_NODE
       * CUSTOMER_NODE_BILL_RUN

[Contents]

* * *

## Tables Referenced

       * INVOICE

[Contents]

* * *

## Functions

       * [bi]BillingInstance$
       * [bi]BillRunFetchById&
       * [bi]BillRunInsert&
       * biBillRunSearchAndFetch&
       * [bi]BillRunUpdate&
       * biBillRunExecute&
       * biBillRunExecute& (With rental effective date)
       * biBillRunImmediate&
       * biBillRunExecuteForCustomer&
       * biBillRunTemplateOperation&
       * biBillRunOperationError&
       * [bi]BillRunOperationFetchById&
       * [bi]BillRunOperationInsert&
       * biBillRunOperationSearchAndFetch&
       * [bi]BillRunOperationUpdate&
       * biBillRunOperationNetSummary& (Maintained in the Client Bill Run Details Form SAS)
       * BillRunOperationNetSummaryQueryLimit&
       * biBillRunOperationSummarySearchAndFetch&
       * biBillRunStop&
       * [bi]BillRunSummary?{}
       * BillRunStatistics?{}
       * BillRunLogStatistics&
       * biBillRunRentalAdjustmentGenerate&
       * biBillRunRentalGenerate&
       * biBillRunRentalGenerate&(2)
       * biBillRunInvoiceGenerate&
       * biQuoteBillRunRentalAdjustmentGenerate&
       * biQuoteBillRunRentalGenerate&
       * biQuoteBillRunInvoiceGenerate&
       * biBillRunInvoicePrepaidGenerate&
       * biBillRunInvoiceImageGenerate&
       * biBillRunInvoiceImagePrepaidGenerate&
       * biBillRunInvoiceConsolidate&
       * biBillRunInvoiceApply&
       * biBillRunInvoiceAllocate&
       * biBillRunInvoicePrint&
       * biBillRunRentalRevoke&
       * biBillRunInvoiceRevoke&
       * biBillRunInvoiceImageRevoke&
       * biBillRunInvoiceImageMinimalRevoke&
       * biBillRunInvoiceConsolidateRevoke&
       * biBillRunInvoiceUnApply&
       * biBillRunInvoiceDeallocate&
       * biBillRunInvoicePrintRevoke&
       * biBillRunInvoicePrintMinimalRevoke&
       * biBillRunRentalAdjustmentGenerateCorporate&
       * biBillRunRentalGenerateCorporate&
       * biBillRunRentalGenerateCorporate&(2)
       * biBillRunInvoiceGenerateCorporate&
       * biBillRunInvoiceImageGenerateCorporate&
       * biBillRunInvoiceGenerateHighVolume&
       * biBillRunRentalAdjustmentGenerateInterim&
       * biBillRunRentalGenerateInterim&
       * biBillRunInvoiceGenerateInterim&
       * biBillRunRentalAdjustmentGenerateCurrentOnly&
       * biBillRunRentalGenerateArrears&
       * biBillRunInvoiceRevokeParallel&
       * BillRunMaxRevokeErrorsPerBatch&
       * BillRunInvoicePrepaidUsageChargesBeforeBillDate&  

       * BillRunInvoicePrepaidMaxErrorsPerBatch&
       * BillRunZeroAdjustmentType?{}  

[Contents]

* * *

### Function [bi]BillingInstance$

**Declaration**

        
                [bi]BillingInstance$(EntityId&, CustomerLookup&)

**Parameters**

EntityId& | IN:  The unique internal identifier of the entity for which a billing instance name is required.  
---|---  
CustomerLookup& | IN: Flag to indicate that the entity is a CUSTOMER_NODE entity.  
  
**Returns**

The instance name on which billing operations will be performed for the entity
with the given EntityId&.

**Description**

Gets the partition number in which the entity should be stored from either the
CustomerPartitionException or CustomerPartitionRange DA tables (see
Implementation for details).  This partition number is then used to get the
required instance name from the CustomerPartition DA table.

In a single instance environment an undefined EPM string is returned for the
instance name.

The EntityId& must correspond to an entity that has its partition range
defined in the CustomerPartitionRange DA table (e.g. CUSTOMER_NODE or
BILL_RUN).

**Implementation**

The "bi" version of this function (biBillingInstance$) is implemented as a
remote function wrapper around the BillingInstance$ EPM function.

If the CustomerLookup& flag is TRUE the CustomerPartitionException DA table is
checked.  If there is a Customer Node Id entry in this DA table matching the
EntityId& the partition number for this entry is the partition number in which
the CUSTOMER_NODE  should be stored.

If the entity is not a CUSTOMER_NODE entity with an entry in
CustomerPartitionException a lookup of the CustomerPartitionRange DA table is
performed to get the partition number in which an entity with the given
EntityId& should be stored.

The retrieved partition number is then used to lookup the CustomerPartition DA
table to get the Rating Instance name for the partition.  This name is
returned by the function.

[Contents][Functions]

* * *

### Function [bi]BillRunFetchById&

**Declaration**

        
                [bi]BillRunFetchById&(BillRunId&,
                            const FieldNames$[],
                            var FieldValues?[])

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be retrieved.  
---|---  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_TRE_V view to be retrieved.  
FieldValues?[] | OUT:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

1 if bill run was found, and the values of the fields whose names were passed
in the _FieldNames$[]_ array are returned in the corresponding
_FieldValues?[]_ array.  
0 if bill run was not found, and the field type arrays are empty.

An error is raised if invalid field names are requested.

**Description**

Returns the details for the bill run with the specified _BillRunId &.  _A list
of valid field names to retrieve can be found in the view BILL_RUN_TRE_V.  The
names of these fields are passed in the _FieldNames$[]_ array.

**Implementation**

The "bi" version of this function (ie, biBillRunFetchById&) is implemented as
a wrapper around the BillRunFetchById& EPM callback function.  The
BillRunFetchById& function is an instantiation of the FetchByIdFuncNDRx class.

[Contents][Functions]

* * *

### Function [bi]BillRunInsert&

**Declaration**

        
                [bi]BillRunInsert&(var LastModified~,
                         const FieldNames$[],
                         const FieldValues?[])

**Parameters**

LastModified~ | OUT:  The last modified date and time stamp of the bill run.  
---|---  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_TRE_V view whose values are to be inserted.  
FieldValues?[] | IN:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

The ID of the inserted bill run on success, with the LAST_MODIFIED date of
this new record returned in _LastModified~_.  An error is raised otherwise.

**Description**

The biBillRunInsert& TRE function inserts a new bill run record.  A list of
valid field names to insert can be found in the view BILL_RUN_TRE_V.  The
names of these fields are passed in the _FieldNames$[]_ array, and the values
corresponding to the names of the fields to insert are passed in the
_FieldValues?[]_ array.  If not specified, the identifier, and hence the
partition, of the created bill run is derived from the partition of (in order
of priority) the BILLING_SCHEDULE_ID, the CREATION_TASK_ID, or the instance
performing the insert ($ATA_INSTANCE). If specified, RENTAL_EFFECTIVE_DATE
should be set to one of the following otherwise an error is raised.

       * Any date of the previous month from the bill run effective date. 
       * Any date of the next month from the bill run effective date. 
       * Any date of the same month as the bill run effective date. 

**Implementation**

The "bi" version of this function (ie, biBillRunInsert&) is implemented as a
wrapper around the BillRunInsert& EPM callback function.  The BillRunInsert&
function is implemented using the BillRunInsertFunc class, which inherits from
the SvcTreInsertFunc class.

[Contents][Functions]

* * *

### Function biBillRunSearchAndFetch&

**Declaration**

        
                biBillRunSearchAndFetch&(WhereClause$,
                                 OrderByClause$,
                                 ParamNames$[],
                                 ParamValues?[],
                                 FromRow&,
                                 ToRow&,
                                 FieldNames$[],
                                 var Rows?[])

**Parameters**

WhereClause$ | IN:  SQL Where clause used to specify search criteria based on specific values in the BILL_RUN_TRE_V.  
---|---  
OrderByClause$ | IN:  Optional SQL Order By clause used by the search query.  
ParamNames$[] | IN:  Names of any parameters used within WhereClause$  
ParamValues?[] | IN:  The corresponding parameter values in the same order as they were specified in ParamNames$[].  
FromRow& | IN:  First row to return.  Rows start from 1.  
ToRow& | IN:  Last row to return. Specify -1 to retrieve all remaining rows.  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_TRE_V view whose values are to be retrieved.  
Rows?[] | OUT:  The result rows returned in a two dimensional array in row, column order. Each rows value's are in the same order that their names were specified in FieldNames$[]  
  
**Returns**

    a) An exception (Error message) if the prepare, any of the binds, or the execute fails, or (_ToRow &_ > 0 and _ToRow &_ < _FromRow &_) or _FromRow &_ < 1.
    b) 0 if no rows are returned. 
    c) The number of rows returned + 1 if there are rows after _ToRow &_ (this implies that the module must do an additional fetch after _ToRow &_ to see if there is additional data). 
    d) The number of rows returned otherwise. 

**Description**

The biBillRunSearchAndFetch& function, performs a search and fetch operation
on the BILL_RUN_TRE_V view.     The search is carried out on the
BILL_RUN_TRE_V view using the _WhereClause$_ and _OrderByClause$_ specified,
with any parameter names and values used in the query specified in
_ParamNames$[]_ and _ParamValues?[]_ respectively.  The number of rows
returned can be limited by specifying a _FromRow &_, and a _ToRow &_.    The
names of the fields to retrieve are passed in the _FieldNames$[]_ array.   A
list of valid field names that can be retrieved can be found in the
BILL_RUN_TRE_V view.  The result row values are passed back in the two
dimensional array _Rows?[]_ in row,column order.

**Implementation**

The biBillRunSearchAndFetch& function is implemented as a remote EPM
(Expression Parser Module) function.  It makes a single call to a private EPM
built-in function called zbiSearchAndFetch&.

[Contents][Functions]

* * *

### Function [bi]BillRunUpdate&

**Declaration**

        
                [bi]BillRunUpdate&(BillRunId&
                         var LastModified~,
                         const FieldNames$[],
                         const FieldValues?[])

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be updated.  
---|---  
LastModified~ | IN:  The last modified date and time stamp of the bill run.  
OUT:  The new last modified date and time stamp of the updated bill run.  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_TRE_V view whose values are to be updated.  
FieldValues?[] | IN:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

Returns 1 if successful. Raises an error otherwise.

**Description**

The biBillRunUpdate& function updates the bill run record for the _BillRunId
&_ specified. The _LastModified~_ parameter must be set to the LAST_MODIFIED
date of the record to be updated. A list of valid field names to update can be
found in the view BILL_RUN_TRE_V.  The names of these fields are passed in the
_FieldNames$[]_ array, and the values corresponding to the names of the fields
to update are passed in the _FieldValues?[]_ array.  
  
If this function is called with the UPDATE_STATISTICS_IND_CODE field set to 1
the _summary function_ for this _bill run type_ is called. The default summary
function used by the Bill Run Types is biBillRunSummary?{}. The results it
returns are used to update the SUMMARY_STATUS_CODE and GENERAL_STATS1 to
GENERAL_STATS10 columns. If this function is called to either set
RENTAL_EFFECTIVE_DATE or update, it can be either of the following otherwise
an error is raised.  

       * Any date of the previous month from the bill run effective date. 
       * Any date of the next month from the bill run effective date. 
       * Any date of the same month as the bill run effective date. 

If this function is called to update bill run effective date when rental
effective date is already set (or rental effective date is also updated with
bill run effective date), rental effective date should always follow above
mentioned condition with respect to bill run effective date.

**Implementation**

The "bi" version of this function (ie, biBillRunUpdate&) is implemented as a
wrapper around the BillRunUpdate& EPM callback function.  The BillRunUpdate&
function is implemented using the BillRunUpdateFunc class which is derived
from the SvcTreUpdateFunc class.  

Any update to the CUSTOMER_COUNT field and the call to the summary function
are both performed using the BillRunSummaryFnRel class which is derived from
the Relation class. The relation is triggered on the
UPDATE_STATISTICS_IND_CODE field being set. The CUSTOMER_COUNT is updated
before the call to the summary function.

[Contents][Functions]

* * *

### Function biBillRunExecute&

**Declaration**

        
                biBillRunExecute&(BillRunId&,
                          Effectivedate~,
                          EffectiveDayOfMonth&,
                          QAInd&,
                          BillingConfiguration&,
                          TaskId&,
                          ProcessName$,
                          FromOperation&,
                          ToOperation&,
                          ErrorThreshold&,
                          RootCustomerNodeList&[],
                          SkipCustomerNodeList&[],
                          [MinimalRevoke&],
                          var SuccessCustomerNodeList&[],
                          var ErrorCustomerNodeList&[],
                          var SuppressedCustomerNodeList&[])

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be executed.  
---|---  
EffectiveDate~ | IN: The effective date/time of the bill run.  
EffectiveDayOfMonth& | IN: The target day of the month to calculate any recurring charges for this bill run.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter, due to some  months not having enough days in them.  See BILL_RUN_TRE_V.EFFECTIVE_DAY_OF_MONTH field for more details.  
QAInd& | IN: Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run.  
BillingConfiguration& | IN: Code that is used to determine the billing operations and subsequent calling programs for a given billing configuration.  The default configuration is given the value '0' with user defined configurations given other positive integer values.    
TaskId& | IN: Task identifier of the set of operations (may be undefined).  
**Note:** One and only one of the TaskId& and ProcessName$ must be defined.  
ProcessName$ | IN: Process/function name that requested the set of operations (may be undefined)  
**Note:** One and only one of the TaskId& and ProcessName$ must be defined.  
FromOperation& | IN: First operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.**  
Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
ToOperation& | IN: Last operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.  
**Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
ErrorThreshold& | IN: Maximum number of overall errors encountered by the program before aborting with a threshold error.  
RootCustomerNodeList&[] | IN: The list of root customer node Ids which the operation calling programs must process. The list will contain a single entry in the case of an on-demand operation calling program.  The customer nodes in this list must be mutually exclusive to the customer nodes in the _SkipCustomerNodeList &[]._  
SkipCustomerNodeList&[] | IN: The list of root customer node Ids which the operation calling programs doesn't process.  The customer nodes in this list must be mutually exclusive to the customer nodes in the _RootCustomerNodeList &[]._  
MinimalRevoke& | IN: Optional Boolean indicating whether minimal revoke functionality should be performed if this operation fails.  If not specified it will default to FALSE.   
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that were successfully processed by all of the operation calling programs.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that were not successfully processed by any of the operation calling programs.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer Ids that have had their invoices suppressed.   See INVOICE.SUPPRESS_IND_CODE for more details on suppressed invoices.  
  
**Returns**

Returns 1 if successful. Otherwise raises an error indicating that the overall
error threshold has been exceeded and aborts.

**Description**

The function biBillRunExecute& is effectively a bill run controller EPM
function.  This function performs the specified range of applicable billing
operations on the specified set of root customer nodes for the specified bill
run.  The operation codes supported by this function are in the range of 1 to
127 for standard billing operations with codes greater than 128 effectively
undoing the effect of that operation.  Both the _FromOperation &_ and
_ToOperation &_ codes must be less than 128 or greater than 128.  Refer to
BILL_RUN_OPERATION_TRE_V for what the operation codes refer to.  The
operations are performed in numerical order for codes less than 128 and in
reverse numerical order for codes above 128.

Only root customers who successfully complete an operation are eligible for
subsequent operations.  If an operation fails altogether, then the
BILL_RUN_OPERATION table must be updated to reflect this and this function
fails all together.  If after an operation the total number of customers in
error is greater than or equal to the _ErrorThreshold &_, then the bill run
controller aborts with an error indicating that the overall error threshold
has been exceeded.

The _BillingConfiguration &_ code is used as the first index value called
"BillingConfiguration" into a Derived Attribute (DA) Table called
"BillingConfiguration".  This code enables the grouping together of the
desired billing operation codes to be performed for a specific configuration.
The "BillingConfiguration" table must be configured to consist of two index
values and one result value.  The second index value called "Bill Run
Operation" contains the billing operation code as referenced in the
BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.  The result value
called "Bill Run Operation Function" contains the name of the billing function
to be called by a successful match of the two key index values.

An example configuration rows added to the "BillingConfiguration" table is
shown below:

> > BillingConfiguration  
>  (INDEX_VALUE1) | Bill Run Operation  
>  (INDEX_VALUE2) | Bill Run Operation Function  
>  (RESULT_VALUE1)  
>> ---|---|---  
>> 5 | 20 | UserXRentalGenerate&  
>> 5 | 30 | UserXInvoiceGenerate&  
>> 5 | 40 | UserXImageGenerate&  
>> 5 | 41 | UserXDefinedFunc&  
  
Note: Only those billing operation codes to be overridden from the default
configuration or any user defined billing operation codes need to be added in
the DA Table.

If the MinimalRevoke& parameter is defined as TRUE then:

If the required Bill Run operation matches any "Bill Run Operation" index
value within the Derived Attribute (DA) Table
"BillingConfigurationRevokeSuppress" then the "Bill Run Operation Function"
result value will be used in preference to the function defined within the
"BillingConfiguration" DA Table. The "BillingConfigurationRevokeSuppress" DA
Table contains revoke operations that keep intermediate results wherever
possible to minimise the amount of work required to complete an operation on a
failed customer hierarchy. For example,  biBillRunInvoiceImageMinimalRevoke&()
keeps any existing completed invoice images associated with a customer
hierarchy. Normally all existing completed invoice images would be deleted.

All billing functions used must lock the all the root customers in
_RootCustomerNodeList &[]_ using the CUSTOMER_NODE table before performing any
billing operations on a customer and unlock them on completion of the
operations.  The billing functions are also responsible for inserting and
updating a CUSTOMER_NODE_BILL_RUN record for each root customer processed for
this billing operation.  They must also update the _SuccessCustomerNodeList
&[]_ with successful root customer node Ids and the _ErrorCustomerNodeList
&[]_ with erred root customer node Ids, depending upon how they performed the
intended billing operation.   The _SuppressedCustomerNodeList &[] _is normally
only populated by the biller ( biInvoiceGenerate& which is wrapped by function
biBillRunInvoiceGenerate&).  The _OperationStatistics?{}_ is updated by the
default billing functions but can be updated by user defined billing
functions.  If the user defined billing function is to update the
_OperationStatistics?{}_ , then bill run entity validation must added as part
of the bill run's type to display these statistics, see
BILL_RUN_TYPE.BILL_RUN_ENTITY_VALIDATION_ID.  The _OperationStatistics?{}_
will consist of a set of key \- value pairs where keys are
BILL_RUN_OPERATION_TRE_V column names and values are the corresponding value
to update the key to.  Updateable column names for statistics are AMOUNT and
GENERAL_STATS1 to GENERAL_STATS10.

Multi-tenancy is supported, however all customers in the
RootCustomerNodeList&[] must belong to the same tenant, or be all un-tenanted.

Note: The parameters referenced in the above paragraph refer only to the
parameters in the following example function <BillingFunctionName> and not
those inNote: The parameters referenced in the above paragraph refer only to
the parameters in the following example function <BillingFunctionName> and not
those in biBillRunExecute&.

All billing operation functions must have the following interface.  If they
complete successfully, they should return the number of successful customers
processed.

> >         <BillingFunctionName>&(BillRunId&,
>                                EffectiveDate~,
>                                EffectiveDayOfMonth&,
>                                BillRunOperationId&,
>                                QAInd&,
>                                RootCustomerNodeList&[],
>         **var** SuccessCustomerNodeList&[],
>         **var** ErrorCustomerNodeList&[],
>         **var** SuppressedCustomerNodeList&[],
>         **var** OperationStatistics?{})
>  

For bill run operation "Rental event generation (RGP), billing operation
functions can have following interface as well."

> >         <BillingFunctionName>&(BillRunId&,
>                                EffectiveDate~,
>                                RentalEffectiveDate~,
>                                EffectiveDayOfMonth&,
>                                BillRunOperationId&,
>                                QAInd&,
>                                RootCustomerNodeList&[],
>         **var** SuccessCustomerNodeList&[],
>         **var** ErrorCustomerNodeList&[],
>         **var** SuppressedCustomerNodeList&[],
>         **var** OperationStatistics?{})
>  

The function biBillRunTemplateOperation&() is provided in the core releases as
an example of how to write a function to perform a new billing operation.

**Implementation**

The biBillRunExecute& function is implemented as a remote EPM (Expression
Parser Module) function.

The basic algorithm is as follows:

> _1.   Do some basic sanity checking on the passed parameters._

> _A valid day of month is passed for EffectiveDayOfMonth &;  
>  One and only one of the TaskId& and ProcessName$ must be defined;  
>  Both the FromOperation& and ToOperation& codes must be less than 128 or
> greater than 128;  
>  FromOperation& code must be less than the ToOperation& code;  
>  The customer nodes in the RootCustomerNodeList&[] and
> SkipCustomerNodeList&[] are mutually exclusive;  
>  There exists a Bill Run Operation Function in the BillingConfiguration
> Derived Attribute table for the corresponding Bill Run Operation code.  
>  Each operation configured for BillingConfiguration& has a corresponding
> reverse operation.  See the description of BILL_RUN_OPERATION_CODE _column
> in the BILL_RUN_OPERATION _table for details._

> _2.   If using MultiTenancy, and no Tenant has been set, set the tenant to
> be the tenant of the first Customer in the customer list._
>
> _3\. Get the contents of Billing Configuration DA Table;_
>
> _4.   if (the FromOperation& is less than 128) {_
>

>> _// Standard billing operations to be performed  
>  for (lidx = FromOperation&; lidx < ToOperation&; lidx++) {_
>>

>>> _5.   ProcessCustomers();_

>>>

>>> _6\. if (error count greater than or equal to ErrorThreshold &) { Abort
with an error; }_

>>>

>>> _7\. Update the next set of root customer nodes for processing which is
all successful customers  
>  from the previous operation;_
>>>

>>> _8\. Append customers   to the progressive copies of the error and
suppressed customers node lists;_

>>>

>>> _9\. Undefine all var parameters from the ProcessCustomers() function;_

>>

>> _} end for_

>
> _}  
>  else  // The FromOperation& is greater than or equal to 128 {_
>

>> _// Reverse billing operations to be performed  
>  for (lidx = ToOperation; lidx > FromOperation; lidx--) {_
>>

>>> _5a.  i_f (MinimalRevoke& is TRUE)  
>       { Use specified function _if billing operation exists in_
> BillingConfigurationRevokeSuppress DA Table }_;_
>>>

>>> _5b.   ProcessCustomers();_

>>>

>>> _6.   if (error count greater than or equal to ErrorThreshold&) { Abort
with an error; }_

>>>

>>> _7\. Update the next set of root customer nodes for processing which is
all successful customers  
>  from the previous operation;_
>>>

>>> _8\. Append customers   to the progressive copies of the error and
suppressed customers node lists;_

>>>

>>> _9\. Undefine all var parameters from the ProcessCustomers() function;_

>>

>> _} end for_

>
> _} end if / else_
>
> _10.   Set up any var parameters before finishing;_
>
> _11.   return 1;_
>
> Algorithm methods:
>
> _ProcessCustomers () {_
>

>> _1\. Insert a new bill run operation including the Pre Skip Count in
the_BILL_RUN_OPERATION _table which  
>  is the number of customers in the SkipCustomerNodeList&[] array;_
>>

>> _2\. Process the customer nodes in SkipCustomerNodeList &[] and insert
their skipped operation into the  _CUSTOMER_NODE_BILL_RUN _table;   // Do not
do anything more with these customers;_

>>

>> _3\. try {_

>>

>>> _Evaluate the billing function passed to this function;_

>>

>> _} except {_

>>

>>> _Update the_BILL_RUN_OPERATION _record to failure, clean up any locked
customers and  
>  re-derive some of the basic statistics;  
>  Abort with error;_
>>

>> _} // end try / except block_

>>

>> _4\. if (a bill run operation was inserted and processed) {_

>>

>>> _5\. Check for any new errors after processing;  
>  Update the various customer counts;_
>>>

>>> _6\. Update the_BILL_RUN_OPERATION _record with count fields, amount,
statistics and status.  
>  If there were erred customer nodes, update the status to warning, else
> update it to success;_
>>

>> _} // end if_

>>

>> _return the number of error customers;_

>
> _} end ProcessCustomers()_

[Contents][Functions]

* * *

### Function biBillRunExecute& (With rental effective date)

**Declaration**

        
                biBillRunExecute&(BillRunId&,
                          Effectivedate~,
                          RentalEffectiveDate~,
                          EffectiveDayOfMonth&,
                          QAInd&,
                          BillingConfiguration&,
                          TaskId&,
                          ProcessName$,
                          FromOperation&,
                          ToOperation&,
                          ErrorThreshold&,
                          RootCustomerNodeList&[],
                          SkipCustomerNodeList&[],
                          MinimalRevoke&,
                          var SuccessCustomerNodeList&[],
                          var ErrorCustomerNodeList&[],
                          var SuppressedCustomerNodeList&[])

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be executed.  
---|---  
EffectiveDate~ | IN: The effective date/time of the bill run.  
RentalEffectiveDate~ | IN: Date-time for rental charge period calculations.  In the variants of this interface without this parameter, the EffectiveDate~ parameter is used to as the Date-time for rental charge period calculations. The variant of this interface with this parameter allows a different date from the bill run Effective Date to be used for rental charge period calculations. This provides a way for bill runs to be performed that have their rentals offset from the usage that is billed.  
EffectiveDayOfMonth& | IN: The target day of the month to calculate any recurring charges for this bill run.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter, due to some  months not having enough days in them.  See BILL_RUN_TRE_V.EFFECTIVE_DAY_OF_MONTH field for more details.  
QAInd& | IN: Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run.  
BillingConfiguration& | IN: Code that is used to determine the billing operations and subsequent calling programs for a given billing configuration.  The default configuration is given the value '0' with user defined configurations given other positive integer values.    
TaskId& | IN: Task identifier of the set of operations (may be undefined).  
**Note:** One and only one of the TaskId& and ProcessName$ must be defined.  
ProcessName$ | IN: Process/function name that requested the set of operations (may be undefined)  
**Note:** One and only one of the TaskId& and ProcessName$ must be defined.  
FromOperation& | IN: First operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.**  
Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
ToOperation& | IN: Last operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.  
**Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
ErrorThreshold& | IN: Maximum number of overall errors encountered by the program before aborting with a threshold error.  
RootCustomerNodeList&[] | IN: The list of root customer node Ids which the operation calling programs must process. The list will contain a single entry in the case of an on-demand operation calling program.  The customer nodes in this list must be mutually exclusive to the customer nodes in the _SkipCustomerNodeList &[]._  
SkipCustomerNodeList&[] | IN: The list of root customer node Ids which the operation calling programs doesn't process.  The customer nodes in this list must be mutually exclusive to the customer nodes in the _RootCustomerNodeList &[]._  
MinimalRevoke& | IN: Optional Boolean indicating whether minimal revoke functionality should be performed if this operation fails.  If not specified it will default to FALSE.   
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that were successfully processed by all of the operation calling programs.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that were not successfully processed by any of the operation calling programs.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer Ids that have had their invoices suppressed.   See INVOICE.SUPPRESS_IND_CODE for more details on suppressed invoices.  
  
**Returns**

Returns 1 if successful. Otherwise raises an error indicating that the overall
error threshold has been exceeded and aborts.

**Description**

The function is similar to biBillRunExecute& with additional ability of taking
rental effective date as parameter. With this function, rental effective date
can be used for generating rental charge period instead of bill run effective
date.

[Contents][Functions]

* * *

### Function biBillRunImmediate&

**Declaration**

        
                biBillRunImmediate&(CustomerNodeId&,
                            FieldNames$[],
                            FieldValues?[],
                            FromOperation&,
                            ToOperation&)
        

**Parameters**

CustomerNodeId& | IN:  The unique internal identifier of the root node of the customer hierarchy for which this immediate bill run is being performed.  
---|---  
FieldNames$[] | IN:  Set of fields in BILL_RUN_TRE_V for specifying details of the immediate bill run that is to be created.  
FieldValues?[] | IN: Corresponding values to the fields specified in FieldNames$[].  These should be of the appropriate data types as specified in BILL_RUN_TRE_V.  
FromOperation& | IN: First operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE.**  
**  
ToOperation& | IN: Last operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.  
**Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
  
**Parameter Notes**

These fields of BILL_RUN_TRE_V will be defaulted if not specified:

BILL_RUN_TYPE_ID     | default to 3, which is "Immediate Bill Run"  
---|---  
EFFECTIVE_DATE | default to current date  
BILLING_SCHEDULE_ID | default to undefined if CREATION_TASK_ID is defined but BILLING_SCHEDULE_ID is not defined  
CUSTOMER_COUNT | default to 1  
STATUS_CODE | default to value returned by ReferenceCodeByLabel&('TASK_STATUS','PENDING')  
SUMMARY_STATUS_CODE | default to value returned by ReferenceCodeByLabel&('TASK_STATUS','PENDING')  
  
**Returns**

Returns the Id of the immediate bill run created if successful. Otherwise
raises an error indicating why the bill run failed.

**Description**

This function creates an immediate bill run and performs the specified range
of operations on it for a customer hierarchy.  Both standard and quality
assurance bill runs can be performed.  If  empty FieldNames$[] and
FieldValues?[]   parameters are provided, it will perform an immediate bill
run of type "Immediate Bill Run" with an effective date equal to the current
date and time.

**Implementation**

This function is implemented as a remote EPM function.  After validating its
parameters it calls biBillRunInsert&() to create a bill run, and then
biBillRunExecuteForCustomer&() to perform the specified set of operations on
it.

[Contents][Functions]

* * *

### Function biBillRunExecuteForCustomer&

**Declaration**

        
                biBillRunExecuteForCustomer&(BillRunId&,
                                     CustomerNodeId&,
                                     TaskId&,
                                     ProcessName$,
                                     FromOperation&,
                                     ToOperation&,
                                     [MinimalRevoke&])
        

**Parameters**

BillRunId& | IN:  The unique identifier of an existing bill run for which a range of operations is to be performed.  
---|---  
CustomerNodeId& | IN:  The unique internal identifier of the root node of the customer hierarchy for this range of operations is to be performed on this bill run.  
TaskId& | IN: The unique internal identifier of the task that was requested these operations to be performed.  
ProcessName$ | IN: The name of the process that requested these operations to be performed.**Note:** Only one of TaskId& or ProcessName$ should contain a defined value.**  
**  
FromOperation& | IN: First operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE.**  
**  
ToOperation& | IN: Last operation of the range of calling programs to process.   Operation codes supported by this function are found in the BILL_RUN_OPERATION_TRE_V.BILL_RUN_OPERATION_CODE field.  
**Note:** Both the FromOperation& and ToOperation& codes must be less than 128
or greater than 128.  
MinimalRevoke& | IN: Optional Boolean indicating whether minimal revoke functionality should be performed if this operation fails.  If not specified it will default to FALSE.   
  
**Returns**

Returns TRUE if the set of operations were successfully performed on the bill
run. An error is raised otherwise.

**Description**

This function performs the specified range of operations on an existing bill
run for a single customer hierarchy.  

**Implementation**

This function is implemented as a remote EPM function.  After validating its
parameters, it calls biBillRunUpdate&() to update the bill run to a running
status, and then biBillRunExecute&() - interface with rental effective date to
perform the specified set of operations on it.  Once biBillRunExecute&()
returns, biBillRunUpdate&() is called at the end to update the bill run to a
success or failure status as appropriate.

[Contents][Functions]

* * *

### Function biBillRunTemplateOperation&

**Declaration**

        
                biBillRunTemplateOperation&(BillRunId&,
        			    EffectiveDate~,
        			    EffectiveDayOfMonth&,
        			    BillRunOperationId&,
        			    QAInd&,
        			    RootCustomerNodeList&[],
        			    var SuccessCustomerNodeList&[],
        			    var ErrorCustomerNodeList&[],
            			    var SuppressedCustomerNodeList&[],
        			    var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be executed.  
---|---  
EffectiveDate~ | IN: The effective date/time of the bill run.  
EffectiveDayOfMonth& | IN: The target day of the month to calculate any recurring charges for this bill run.  This may not be the same as the day of month as supplied by the EffectiveDate~ parameter, due to some  months not having enough days in them.  See BILL_RUN_TRE_V.EFFECTIVE_DAY_OF_MONTH field for more details.  
BillRunOperationId& | IN:  The unique internal identifier of the bill run operation to be retrieved.  
QAInd& | IN: Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run.  
RootCustomerNodeList&[] | IN: The list of root customer node Ids which the operation calling programs must process.   
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that were successfully processed by all of the operation calling programs.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that were not successfully processed by any of the operation calling programs.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer Ids that have had their invoices suppressed.    
OperationStatistics?{} | OUT: A list  to populate Operation Statistics if needed.  
  
**Returns**

Returns TRUE if successful. An error is raised otherwise.

**Description**

This is a template EPM function for billing operations  provided in the core
releases as an example of how to write a function to perform a new billing
operation.

**Implementation**

This function is implemented as a remote EPM function.

[Contents][Functions]

* * *

### Function biBillRunOperationError&

**Declaration**

        
                biBillRunOperationError&(BillRunOperationId&,
                                 var LastModified~,
        			 ErrorMessageId&,
        			 const ErrorMessage$)
        

**Parameters**

BillRunOperationId& | IN:  The unique internal identifier of the bill run operation to be retrieved.  
---|---  
LastModified~ | IN:  The last modified date and time stamp of the bill run operation.  
OUT:  The new last modified date and time stamp of the updated bill run
operation.  
ErrorMessageId& | IN:  The identifier of the error message explaining why this bill run operation has failed.  
ErrorMessage$ | IN:  The text of the error message explaining why this bill run operation has failed.  
  
**Returns**

1 if successful.  An error is raised otherwise.

**Description**

The function is called by biBillRunExecute&() to handle the failure of a bill
run operation.  It should not have to be called directly.  This function:

      1. Finds all root customers associated with this bill run with a status of 'Running' and updates them to a status of failure.
      2. Unlocks all customers currently locked by this bill run operation.
      3. Re-derives some of the statistics associated with this bill run operation to reflect how far through the operation the process got before the fatal error occurred.  All the _COUNT statistics are re-derived.  The AMOUNT associated with the operation is not re-derived.  Neither are any of the GENERAL_STATs fields.
      4. Calls the biBillRunOperationUpdate&() to update the bill run operation statistics, status and error details.

Note: If the length of the bill run operation error message is greater than
4000, it is truncated to 4000.

**Implementation**

This function is implemented as a remote EPM function associated with the
biBillRunRW service.  This function is transactional.

[Contents][Functions]

* * *

### Function [bi]BillRunOperationFetchById&

**Declaration**

        
                [bi]BillRunOperationFetchById&(BillRunOperationId&,
                                     const FieldNames$[],
                                     var FieldValues?[])

**Parameters**

BillRunOperationId& | IN:  The unique internal identifier of the bill run operation to be retrieved.  
---|---  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_OPERATION_TRE_V view to be retrieved.  
FieldValues?[] | OUT:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

1 if bill run operation was found, and the values of the fields whose names
were passed in the _FieldNames$[]_ array are returned in the corresponding
_FieldValues?[]_ array.  
0 if bill run operation was not found, and the field type arrays are empty.

An error is raised if invalid field names are requested.

**Description**

Returns the details for the bill run operation with the specified
_BillRunOperationId &.  _A list of valid field names to retrieve can be found
in the view BILL_RUN_OPERATION_TRE_V.  The names of these fields are passed in
the _FieldNames$[]_ array.

**Implementation**

The "bi" version of this function (ie, biBillRunOperationFetchById&) is
implemented as a wrapper around the BillRunOperationFetchById& EPM callback
function.   The BillRunOperationFetchById& function is an instantiation of the
FetchByIdFuncNDRx class.

[Contents][Functions]

* * *

### Function [bi]BillRunOperationInsert&

**Declaration**

        
                [bi]BillRunOperationInsert&(var LastModified~,
                                  const FieldNames$[],
                                  const FieldValues?[])

**Parameters**

LastModified~ | OUT:  The last modified date and time stamp of the bill run operation.  
---|---  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_OPERATION_TRE_V view whose values are to be inserted.  
FieldValues?[] | IN:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

The ID of the inserted bill run operation on success, with the LAST_MODIFIED
date of this new record returned in _LastModified~_.  An error is raised
otherwise.

**Description**

The biBillRunOperationInsert& TRE function inserts a new bill run operation
record. A list of valid field names to insert can be found in the view
BILL_RUN_OPERATION_TRE_V.  The names of these fields are passed in the
_FieldNames$[]_ array, and the values corresponding to the names of the fields
to insert are passed in the _FieldValues?[]_ array.  If not specified, the
identifier, and hence the partition, of the new bill run operation record is
derived from the specified BILL_RUN_ID.

**Implementation**

The "bi" version of this function (ie, biBillRunOperationInsert&) is
implemented as a wrapper around the BillRunOperationInsert& EPM callback
function.   The BillRunOperationInsert& function is implemented using the
BillRunOpInsertFunc class, which inherits from the SvcTreInsertFunc class.

[Contents][Functions]

* * *

### Function biBillRunOperationSearchAndFetch&

**Declaration**

        
                biBillRunOperationSearchAndFetch&(WhereClause$,
                                          OrderByClause$,
                                          ParamNames$[],
                                          ParamValues?[],
                                          FromRow&,
                                          ToRow&,
                                          FieldNames$[],
                                          var Rows?[])

**Parameters**

WhereClause$ | IN:  SQL Where clause used to specify search criteria based on specific values in the BILL_RUN_OPERATION_TRE_V.  
---|---  
OrderByClause$ | IN:  Optional SQL Order By clause used by the search query.  
ParamNames$[] | IN:  Names of any parameters used within WhereClause$  
ParamValues?[] | IN:  The corresponding parameter values in the same order as they were specified in ParamNames$[].  
FromRow& | IN:  First row to return.  Rows start from 1.  
ToRow& | IN:  Last row to return.  Specify -1 to retrieve all remaining rows.  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_OPERATION_TRE_V view whose values are to be retrieved.  
Rows?[] | OUT:  The result rows returned in a two dimensional array in row, column order. Each rows value's are in the same order that their names were specified in FieldNames$[]  
  
**Returns**

    a) An exception (Error message) if the prepare, any of the binds, or the execute fails, or (_ToRow &_ > 0 and _ToRow &_ < _FromRow &_) or _FromRow &_ < 1\. 
    b) 0 if no rows are returned. 
    c) The number of rows returned + 1 if there are rows after _ToRow &_ (this implies that the module must do an additional fetch after _ToRow &_ to see if there is additional data). 
    d) The number of rows returned otherwise. 

**Description**

The biBillRunOperationSearchAndFetch& function, performs a search and fetch
operation on the BILL_RUN_OPERATION_TRE_V view.  The search is carried out on
the BILL_RUN_OPERATION_TRE_V view using the _WhereClause$_ and
_OrderByClause$_ specified, with any parameter names and values used in the
query specified in _ParamNames$[]_ and _ParamValues?[]_ respectively.  The
number of rows returned can be limited by specifying a _FromRow &_, and a
_ToRow &_.   The names of the fields to retrieve are passed in the
_FieldNames$[]_ array.   A list of valid field names that can be retrieved can
be found in the BILL_RUN_OPERATION_TRE_V view.  The result row values are
passed back in the two dimensional array Rows?[] in row,column order.

**Implementation**

The biBillRunOperationSearchAndFetch& function is implemented as a remote EPM
(Expression Parser Module) function.  It makes a single call to a private EPM
built-in function called zbiSearchAndFetch&.

[Contents][Functions]

* * *

### Function [bi]BillRunOperationUpdate&

**Declaration**

        
                [bi]BillRunOperationUpdate&(BillRunOperationId&
                                  var LastModified~,
                                  const FieldNames$[],
                                  const FieldValues?[])

**Parameters**

BillRunOperationId& | IN:  The unique internal identifier of the bill run operation to be updated.  
---|---  
LastModified~ | IN:  The last modified date and time stamp of the bill run operation.  
OUT:  The new last modified date and time stamp of the updated bill run
operation.  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_OPERATION_TRE_V view whose values are to be updated.  
FieldValues?[] | IN:  Field values, in the same order that their names were specified in FieldNames$[].  
  
**Returns**

Returns 1 if successful. Raises an error otherwise.

**Description**

Updates the bill run operation record for the _BillRunOperationId &_
specified. The _LastModified~_ parameter must be set to the LAST_MODIFIED date
of the record to be updated. A list of valid field names to update can be
found in the view BILL_RUN_OPERATION_TRE_V.  The names of these fields are
passed in the _FieldNames$[]_ array, and the values corresponding to the names
of the fields to update are passed in the _FieldValues?[]_ array.

**Implementation**

The "bi" version of this function (ie, biBillRunOperationUpdate&) is
implemented as a wrapper around the BillRunOperationUpdate& EPM callback
function.   The BillRunOperationUpdate& function is implemented using the
BillRunOpUpdateFunc class which is derived from the SvcTreUpdateFunc class.  

[Contents][Functions]

* * *

### Function BillRunOperationNetSummaryQueryLimit&

**Declaration**

        
                BillRunOperationNetSummaryQueryLimit&()

**Parameters**

None

**Returns**

A limit to decide whether CUSTOMER_NODE_BILL_RUN is queried by
biBillRunOperationNetSummary& to adjust for partially revoked operations.

**Description**

To adjust the results for partially revoked operations in
biBillRunOperationNetSummary&(), CUSTOMER_NODE_BILL_RUN is queried for each
operation code.

The total of INPUT_COUNT for all operations that had errored, skipped or
suppressed customers is calculated. The INPUT_COUNT for any successful revokes
after the first operation for an operation code that had errored, skipped or
suppressed customers is added to the total.

If the total exceeds the value returned by this function,
CUSTOMER_NODE_BILL_RUN is not queried, and the net values of SUCCESS_COUNT,
ERROR_COUNT, PRE_SKIP_COUNT and POST_SKIP_ACCOUNT are not adjusted for partial
revokes for any operation code..

If the adjustment is not performed, message  is written to the system log.

If the return value is -1, no limit applies and CUSTOMER_NODE_BILL_RUN is
always queried.

The default return value is 2,250,000.

**Implementation**

This is a BASE_INSTALL function that is able to be modified by configurers.

[Contents][Functions]

* * *

### Function biBillRunOperationSummarySearchAndFetch&

**Declaration**

        
                biBillRunOperationSummarySearchAndFetch&(WhereClause$,
                                                 OrderByClause$,
                                                 ParamNames$[],
                                                 ParamValues?[],
                                                 FromRow&,
                                                 ToRow&,
                                                 FieldNames$[],
                                                 var Rows?[])

**Parameters**

WhereClause$ | IN:  SQL Where clause used to specify search criteria based on specific values in the BILL_RUN_SUMMARY_TRE_V.  
---|---  
OrderByClause$ | IN:  Optional SQL Order By clause used by the search query.  
ParamNames$[] | IN:  Names of any parameters used within WhereClause$  
ParamValues?[] | IN:  The corresponding parameter values in the same order as they were specified in ParamNames$[].  
FromRow& | IN:  First row to return.  Rows start from 1.  
ToRow& | IN:  Last row to return.  Specify -1 to retrieve all remaining rows.  
FieldNames$[] | IN:  Names of the fields from the BILL_RUN_SUMMARY_TRE_V view whose values are to be retrieved.  
Rows?[] | OUT:  The result rows returned in a two dimensional array in row, column order. Each rows value's are in the same order that their names were specified in FieldNames$[]  
  
**Returns**

    a) An exception (Error message) if the prepare, any of the binds, or the execute fails, or (_ToRow &_ > 0 and _ToRow &_ < _FromRow &_) or _FromRow &_ < 1\. 
    b) 0 if no rows are returned. 
    c) The number of rows returned + 1 if there are rows after _ToRow &_ (this implies that the module must do an additional fetch after _ToRow &_ to see if there is additional data). 
    d) The number of rows returned otherwise. 

**Description**

The biBillRunOperationSummarySearchAndFetch& function, performs a search and
fetch operation on the BILL_RUN_SUMMARY_TRE_V view.  The search is carried out
on the BILL_RUN_SUMMARY_TRE_V view using the _WhereClause$_ and
_OrderByClause$_ specified, with any parameter names and values used in the
query specified in _ParamNames$[]_ and _ParamValues?[]_ respectively.  The
number of rows returned can be limited by specifying a _FromRow &_, and a
_ToRow &_.   The names of the fields to retrieve are passed in the
_FieldNames$[]_ array.   A list of valid field names that can be retrieved can
be found in the BILL_RUN_SUMMARY_TRE_V view.  The result row values are passed
back in the two dimensional array Rows?[] in row,column order.

**Implementation**

The biBillRunOperationSummarySearchAndFetch& function is implemented as a
remote EPM (Expression Parser Module) function.  It makes a single call to a
private EPM built-in function called zbiSearchAndFetch&.

[Contents][Functions]

* * *

### Function biBillRunStop&

**Declaration**

        
                biBillRunStop&(BillRunId&,
                       var LastModified~,
                       TaskId&,
                       const Reason$)
        

**Parameters**



BillRunId& | IN:  The unique internal identifier of the bill run to be stopped.  
---|---  
LastModified~ | IN:  The last modified date and time stamp of the bill run.  
OUT:  The new last modified date and time stamp of the updated bill run.  
TaskId& | IN:  The unique identifier of a task that is executing for this bill run and requires its billing operations to be stopped. If an undefined value is passed for this parameter then all operations for the bill run and all tasks associated with these operations are stopped.   
Reason$ | IN:  The reason for stopping the bill run (if any).  This will be used as part of the error message used to update any running operations associated with the bill run.  
  
**Returns**

    1 if successful. An error is raised otherwise.

**Description**

This function can be used to stop a bill run that is in progress.   It
operates by finding those server processes that are currently performing
operations on customers on the bill run, and then signalling those processes
to stop.  Once all processes have stopped operations on the bill run it
updates any operations still with a Running status to an Error status, and
finally updates the bill run itself.

**Implementation**

This function is implemented as a remote EPM function.

If the TaskId& parameter has been specified:

       * It queries the CUSTOMER_NODE table to find the processes and operations associated with the specified bill run and task.
       * Processes that have a lock on the CUSTOMER_NODE records are sent the SIGTERM signal using the ProcessSignal&() built-in function. 
       * After 120 seconds any processes that still hold a lock on a   CUSTOMER_NODE record are sent the SIGQUIT signal. 
       * After a further 120 seconds a process that still holds a lock it is sent the SIGKILL signal.
       * Any bill run operations for the task still in a Running state after the process associated with it has been killed are updated using the  biBillRunOperationError&() function. 

If the TaskId& parameter is undefined or 0:

       * The specified LastModified~ must equal the last modified date for the bill run. 
       * All running tasks for the given BillRunId& are stopped by calling biTaskUpdate& to update the task status to 'Stopping'.  
       * It waits for up to five minutes for the updated tasks to stop. 
       * The steps performed when the TaskId& parameter has been specified are then performed.  Note: there should be no records in the CUSTOMER_NODE associated with the specified bill run as all necessary updates should have been made when the billing tasks stopped.

The biBillRunUpdate&() function is called at the end to indicate that the bill
run has been stopped and to invoke the bill run summary function.

[Contents][Functions]

* * *

### Function [bi]BillRunSummary?{}

**Declaration**

        
                [bi]BillRunSummary?{}(const BillRunDetails?{})

**Parameters**

BillRunDetails?{} | IN:  Details from BILL_RUN_TRE_V of a bill run whose summary status and statistics are to be summarised.  
---|---  
  
**Returns**

    A hash containing the new summary status of the bill run (key SUMMARY_STATUS_CODE) as well as overall statistics for the bill run specified in keys GENERAL_STATS1 to GENERAL_STATS10.

**Description**

This function is used to summarise the status of a bill run and gather
statistics on it.  Its interface is appropriate to allow it to be specified as
the Summary function for Bill Run Types.  It is the default summary function
used by the core Bill Run Types distributed with the Convergent Billing
application.   It can also be used as a template for creating alternative
summary functions.

The function is called as part of biBillRunUpdate&() processing when the
UPDATE_STATISTICS_IND_CODE field is set to 1.  This is normally done on
completion of an operation on a bill run.

The function gathers statistics by querying the BILL_RUN_OPERATION table for
the bill run in question and aggregating the statistics from each operation
performed.   If failed operations are present then some statistics are
gathered by directly querying other tables.

The summary status is determined by examining the number of customers that
have successfully completed each billing operation.  If 80% percent of the
customers have successfully completed that operation, then it considers it
appropriate to update the summary status to indicate that that operation has
been completed successfully.

**Implementation**

BillRunSummary?{} is implemented as a local EPM function.  For each operation,
it gathers the appropriate statistics to summarise at the bill run level.
Statistics for revoke operations are subtracted from the corresponding
generate operation.  It attempts to estimate the number of customers that have
successfully completed each generate operation by assuming that revokes are
performed on error and suppressed customers first.

biBillRunSummary?{} is a remote wrapper around BillRunSummary?{} for backwards
compatibility purposes only.

[Contents][Functions]

* * *

### Function BillRunStatistics?{}

**Declaration**

        
                BillRunStatistics{}(
            const FromBillRunId&,
            const ToBillRunId&,
            const FromBillRunOperationId&,
            const ToBillRunOperationId&,
            const FromLastModified~,
            const ToLastModified~)

**Parameters**

FromBillRunId& | IN:  The inclusive start of the range of bill run ids on which statistics are to be gathered.   
---|---  
ToBillRunId& | IN:  The inclusive end of the range of bill run ids on which statistics are to be gathered.   
FromBillRunOperationId& | IN:  The inclusive start of the range of bill run operation ids on which statistics are to be gathered.   
ToBillRunOperationId& | IN:  The inclusive end of the range of bill run operation ids on which statistics are to be gathered.  
FromLastModified~ | IN:  The inclusive start of the date range of bill run operations for which statistics are to be gathered.   
ToLastModified~ | IN: The inclusive end of the range of bill run operations for which statistics are to be gathered.  
  
**Returns**

    A hash containing the summary of all bill run operations that satisfy the selection criteria.  The results are grouped by Bill Run and  Bill Run Operation.   The table below documents the return structure:
**Key** | **Description**  
---|---  
Instance | The CB Billing instance associated with the collected statistics.  This key is only present if the ATA_INSTANCE environment variable is defined, and either a FromBillRunId to ToBillRunId range is not specified or the specified range is within a single customer partition.  
Parameters | The parameters that were passed to this function. Undefined parameter values are not included.   
| **Key** | **Description**  
---|---  
FromBillRunId | (Integer) See above.  
ToBillRunId | (Integer) See above.  
FromBillRunOperationId | (Integer) See above.  
ToBillRunOperationId | (Integer) See above.  
FromLastModified | (DateTime) See above.  
ToLastModified | (DateTime) See above.  
BillRuns | An array of bill runs for which statistics have been gathered over the specified period.  Each element of the array is a hash containing the following details. | **Key** | **Description**  
---|---  
BillRunId | (Integer) The unique identifier of a bill run.  
BillRunType | (String) The type of this bill run  
BillRunCurrency | (String) The currency used for reporting amounts in this bill run.  
Status | (String) The status of the bill run  
SummaryStatus | (String) The summary status of the bill run  
LastModified | (DateTime) The date and time the bill run record was last updated.  
Operations | An array containing details of any operations that have either started or completed over the period for this bill run.  The operations are grouped and ordered by operation code.  Each element in the array is a hash containing the following keys.   Note that any keys with a zero value will not be included in the hash. | **Key** | **Description**  
---|---  
Operation | (String) The name of the operation.  
OperationCode | (Integer) The numeric code associated with the operation  
Running | (Integer) The number of operations of this type that are currently running with this operation code (not summable).  
Failed | (Integer) The number of operations of this type that failed in the period.  
Success | (Integer) The number of operations that completed successfully in the period  
Warning | (Integer) The number of operations that completed with warning conditions in the period.  
Duration | (Integer) The sum of the duration of operations that have completed in the period.  Includes Failed, Warning and Success operations.  
CustomerRunning | (Integer) The number of customers associated with currently running operations.  
CustomerSuccess | (Integer) The number of customers that have successfully completed this operation in this period  
CustomerError | (Integer) The number of customers that have failed to complete this operation in this period  
CustomerSkipped | (Integer) The number of customers that have skipped this operation in this period.  
CustomerSuppressed | (Integer) The number of customers that were suppressed on completing this operation in this period.  
Amount | (Real) The value of invoices processed by the operations of this type in this period.  This is reported in the BillRunCurrency.   
Invoices (1) | (Integer) The number of invoices successfully processed by this operation in this period.  
Statements (1) | (Integer) The number of statements successfully processed by this operation in this period.  
InvoiceImages (1) | (Integer) The number of invoice images successfully processed by this operation in this period.  
InvoiceImageSizeGz (1) | (Integer) The total size of compressed invoice images generated in this period.  
Nodes (1) | (Integer) The number of customer nodes successfully processed by this operation in this period  
Services (1) | (Integer) The number of services successfully processed by this operation in this period.  
Events (1) | (Integer) The number of events generated or processed by this operation in this period  
ErrorEvents (1) | (Integer) The number of error events generated by this operation in this period.  
ChargesUpdated (1) | (Integer) The number of rating charges updated by this operation in this period  
ChargesInserted (1) | (Integer) The number of billing charges inserted by this operation in this period.  
  
Note 1: These key names (and their descriptions) are actually derived based on
the Bill Run Operation entity validation in use for the Bill Run Type. The
values shown above are where the core supplied evBILL_RUN_OPERATION entity
validation is being used.  The key names are derived from the Attribute Type
Names being used, not their Labels, so that the keys should be language
independent.The key names are derived by stripping the Attribute Type Names of
their "BILL_RUN_" prefix and converting them to leading-uppercase.  
NextOperationId | (Integer) The next bill run operation id that is safe to pass in as FromBillRunOperationId& in a subsequent call to this function for the next sequential period.  It will equal MIN(MAX(completed operation)+1, MIN(running operation))).  
  


**Description**

This function is used to obtain recent bill run statistics for subsequent
logging to the TREMON process.

For this function to perform efficiently it should be passed either:

       * defined values for both a FromBillRunId& and a ToBillRunId&.
       * a defined value for either (or both) of FromBillRunOperationId and ToBillRunOperationId&.

Otherwise all bill run operations for an instance will be scanned.

When specifying a ToLastModified~ parameter, it is recommended that a date and
time no later than 5 seconds before the current date and time is used.  Using
a larger value could result in bill run operations being missed in the
gathered statistics.

**Implementation**

This function is implemented as a local EPM function.  It performs queries on
the BILL_RUN, BILL_RUN_OPERATION and BILL_RUN_TYPE tables to get the
information required.  The key names to use for  some of the bill run
operation statistics are derived from queries on the ENTITY_VALIDATION and
ATTRIBUTE_TYPE tables.  These key names are cached in the ProcessState?{}
global variable to minimise the cost of repeated calls to this function.

The function asserts that either both FromBillRunId& and ToBillRunId& are
defined or both FromBillRunId& and ToBillRunId& are undefined before
continuing.  If both FromBillRunId& and ToBillRunId& are defined statistics
will be gathered for all bill runs between this range.

If both FromBillRunId& and ToBillRunId& are not defined and both
FromBillRunOperationId& and &ToBillRunOperationId& are not defined, an array
of partition ranges is determined from the current instance to restrict the
statistics to that instance.  The function will iterate through this array,
setting the FromBillRunId& to the start of each partition range and setting
the ToBillRunId& to the end of each partition range, gathering the appropriate
statistics for that partition and accumulating the statistics for the
instance.

If FromBillRunOperationId& is defined only statistics for bill run operations
with a bill_run_operation_id >= FromBillRunOperationId& are selected.  If
ToBillRunOperationId& only statistics for bill run operations with a
bill_run_operation_id < = ToBillRunOperationId& are selected.

If FromLastModified~ is defined only statistics for bill run operations with a
last_modified_date >= FromLastModified~ are selected.  If ToLastModified~ only
statistics for bill run operations with a  last_modified_date <=
ToLastModified~ are selected.

[Contents][Functions]

* * *



### Function BillRunLogStatistics&

**Declaration**

        
                BillRunLogStatistics&(
            FromBillRunId&,
            ToBillRunId&,
            FromLastModified~,
            Period&,
            Iterations&,
            LogToFile&)

**Parameters**

FromBillRunId& | IN:  The inclusive start of the range of bill run ids for which statistics are to be logged.  
---|---  
ToBillRunId& | IN:  The inclusive end of the range of bill run ids for which statistics are to be logged.  
FromLastModified~ | IN: The inclusive start of the date range of bill run operations for which statistics are to be gathered.  Only bill run operations or bill runs with a last modified date on or after this date and time will have their statistics gathered.  
Period& | IN: The period of time in seconds to check for updated bill run statistics and log them.  
Iterations& | IN: The number of times to check for updated bill run statistics.  
LogToFile& | IN: TRUE to log statistics to XML statistics file in addition to tremon memory.  
  
**Returns**

    The number of times that updated bill run statistics were logged.  This will be between 1 and Iterations& times.

**Description**

This function is used to periodically log updated bill run statistics to the
TREMON process.  On its first iteration, it will log bill run statistics for
bill runs with identifiers in the range FromBillRunId& to ToBillRunId&(if both
are defined), or it will log bill run statistics for bill runs on the instance
that this function is running(if neither are defined) that have been modified
between FromLastModified~ and 5 seconds before the current date and time.  The
function BillRunStatistics?{}() is called to obtain the relevant statistics.
All statistics obtained from this function are logged, except for the
'NextOperationId' key.  This key is used in subsequent calls to
BillRunStatistics?{}() to improve its query performance.

Statistics are subsequently obtained every Period& seconds for the range of
bill runs, with a last modified date range from 1 second after the end of the
previously logged range, to 5 seconds before the current date and time.
Messages are output every Period& seconds indicating if there has been any
billing activity in the previous period.

If there has been no billing activity in the period, then no statistics are
logged unless this is the last iteration.  Statistics are always logged on the
last iteration to record that billing statistics were being gathered.
Statistics are logged using 'bill_run' as the process name.

If LogToFile& is set to TRUE, statistics are logged to the XML statistics file
in addition to the Tremon memory.

**Implementation**

This function is implemented as a local EPM function.  It loops Iterations&
times, calling BillRunStatistics?{}() on each iteration and then calling
biMonitorLog&() on those iterations on which there has been some billing
activity. The LogToFile& parameter of biMonitorLog&() is set to the value of
the LogToFile& parameter passed in to this function.

[Contents][Functions]

* * *

### Function biBillRunRentalAdjustmentGenerate&

**Declaration**

        
                biBillRunRentalAdjustmentGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed.  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully. An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the RAP interface of
biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to TRUE then sets the
following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biQuoteBillRunRentalAdjustmentGenerate&

**Declaration**

        
                biQuoteBillRunRentalAdjustmentGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed.  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully. An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the RAP interface of
biQuoteRentalGenerate&. The remote service name of this function is
biQuoteBillRO advertised in a separate TRERODB server for quoting purposes.

**Implementation**

Calls biQuoteRentalGenerate& with AdjustmentInd& set to TRUE then sets the
following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalGenerate&

**Declaration**

        
                biBillRunRentalGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to FALSE then sets the
following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalGenerate&(2)

**Declaration**

        
                biBillRunRentalGenerate&(
        	BillRunId&,
           	EffectiveDate~,
        	RentalEffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
RentalEffectiveDate~ | IN: Date-time for rental charge period calculations.  In the variants of this interface without this parameter, the EffectiveDate~ parameter is used to as the Date-time for rental charge period calculations. The variant of this interface with this parameter allows a different date from the bill run Effective Date to be used for rental charge period calculations. This provides a way for bill runs to be performed that have their rentals offset from the usage that is billed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with RentalEffectiveDate~ and with AdjustmentInd& set
to FALSE then sets the following statistics in the OperationStatistics?{} hash
which is used to populate the bill run operation statistics in the
BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biQuoteBillRunRentalGenerate&

**Declaration**

        
                biQuoteBillRunRentalGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed.  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper of biQuoteRentalGenerate&. The remote
service name of this function is biQuoteBillRO advertised in a separate
TRERODB server for quoting purposes.

**Implementation**

Calls biQuoteRentalGenerate& with AdjustmentInd& set to FALSE then sets the
following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceGenerate&

**Declaration**

        
                biBillRunInvoiceGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed.  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceGenerate&.

**Implementation**

Calls biInvoiceGenerate& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on invoices and statements generated in the bill run operation  
GENERAL_STATS1 | The number of invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements generated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
GENERAL_STATS6 | The number of services that were processed by the bill run operation  
GENERAL_STATS7 | The number of normalised events that were processed by the bill run operation  
GENERAL_STATS9 | The number of original charges that were processed by the bill run operation  
GENERAL_STATS10 | The total number of subtotal and tariff charges generated during the bill run operation  
  
Any customers appearing in SuppressedCustomerNodeList&[] have their invoices
and rentals revoked and the AMOUNT, GENERAL_STATS1, GENERAL_STATS2,
GENERAL_STATS9 and GENERAL_STATS10 statistics adjusted. The total number of
services, events and nodes processed cannot be adjusted so GENERAL_STATS5,
GENERAL_STATS6 and GENERAL_STATS7 are not adjusted.

[Contents] [Functions]

* * *

### Function biQuoteBillRunInvoiceGenerate&

**Declaration**

        
                biQuoteBillRunInvoiceGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed.  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed. For quotes this is always an empty list.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper of biQuoteInvoiceGenerate&. The remote
service name of this function is biQuoteBillRO advertised in a separate
TRERODB server for quoting purposes.

Customers that were returned as suppressed by the call to InvoiceGenerate& are
updated to success by this wrapper function. Quote generation effectively
ignores the flag to suppress invoices.

**Implementation**

Calls biQuoteInvoiceGenerate& then sets the statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.  
This function is similar to biBillRunInvoiceGenerate& function however it does
not perform an invoice revoke and rental event revoke for suppressed
customers.

* * *

### Function biBillRunInvoicePrepaidGenerate&

**Declaration**

        
                biBillRunInvoicePrepaidGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed.  
QAInd& | IN: Must always be FALSE when calling this function. If a value other than FALSE is passed, an error will be raised. QA bill runs are not supported for prepaid with statements billing.  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around  biInvoicePrepaidGenerate&.
biInvoicePrepaidGenerate& will abort if the number of errors detected during
the operation exceeds the threshold provided by
BillRunInvoicePrepaidMaxErrorsPerBatch&.

**Implementation**

Calls biInvoicePrepaidGenerate& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on invoices and statements generated in the bill run operation  
GENERAL_STATS1 | The number of invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements generated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
GENERAL_STATS9 | The number of original charges that were processed by the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceImageGenerate&

**Declaration**

        
                biBillRunInvoiceImageGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  FALSE otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceImageGenerate&.

**Implementation**

Calls biInvoiceImageGenerate& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images generated in the bill run operation  
GENERAL_STATS4 | The total image size (post-compression) in bytes of all invoice images generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceImagePrepaidGenerate&

**Declaration**

        
                biBillRunInvoiceImagePrepaidGenerate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  FALSE otherwise.

**Description**

Billing Configuration compliant wrapper to prevent invoice image generation
for the prepaid billing configuration.

**Implementation**

A dummy function to return all root customer nodes as successful without
generating any invoice images. The function also sets the following statistics
in the OperationStatistics?{} hash which is used to populate the bill run
operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images generated in the bill run operation. This is always set to 0.  
GENERAL_STATS4 | The total image size (post-compression) in bytes of all invoice images generated in the bill run operation. This is always set to 0.  
  
[Contents] [Functions]

* * *

### Function  biBillRunInvoiceConsolidate&

**Declaration**

        
                biBillRunInvoiceConsolidate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceConsolidate&.

**Implementation**

Calls biInvoiceConsolidate& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on consolidated invoices generated in the bill run operation  
GENERAL_STATS1 | The number of consolidated invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements consolidated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceApply&

**Declaration**

        
                biBillRunInvoiceApply&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceApply&.

**Implementation**

Calls biInvoiceApply& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices applied in the bill run operation  
GENERAL_STATS2 | The number of statements applied in the bill run operation  
AMOUNT | The total amount applied in the bill run operation (including invoices and statements)  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceAllocate&

**Declaration**

        
                biBillRunInvoiceAllocate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed if successful. An error is
raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceAllocateCustomers&.

**Implementation**

Calls biInvoiceAllocateCustomers& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices allocated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoicePrint&

**Declaration**

        
                biBillRunInvoicePrint&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoicePrint&.

**Implementation**

Calls biInvoicePrint& with the InvoicePrintConfigItemSeqnr& parameter set to
1.   Sets the following statistics in the OperationStatistics?{} hash which is
used to populate the bill run operation statistics in the BILL_RUN_OPERATION
table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images printed in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalRevoke&

**Declaration**

        
                biBillRunRentalRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biRentalRevoke&.
biRentalRevoke& will abort if the number of errors detected during the
operation exceeds the threshold provided by  BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biRentalRevoke& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events deleted in the bill run operation  
GENERAL_STATS8 | The number of error events deleted in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceRevoke&

**Declaration**

        
                biBillRunInvoiceRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoiceRevoke&.
biInvoiceRevoke& will abort if the number of errors detected during the
operation exceeds the threshold provided by  BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biInvoiceRevoke& then sets the following statistics in the
OperationStatistics?{} parameter which is used to populate the bill run
operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices deleted in the bill run operation  
GENERAL_STATS2 | The number of statements deleted in the bill run operation  
GENERAL_STATS3 | The number of invoice images deleted in the bill run operation  
GENERAL_STATS9 | The number of charges updated in the bill run operation  
GENERAL_STATS10 | The number of charges deleted in the bill run operation  
AMOUNT | The total amount of all invoices revoked in the bill run operation (including invoices and statements)  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceImageRevoke&

**Declaration**

        
                biBillRunInvoiceImageRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoiceImageRevoke&.
biInvoiceImageRevoke& will abort if the number of errors detected during the
operation exceeds the threshold provided by  BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biInvoiceImageRevoke& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images revoked in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceImageMinimalRevoke&

**Declaration**

        
                biBillRunInvoiceImageMinimalRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoiceImageMinimalRevoke&.
biInvoiceImageMinimalRevoke& will abort if the number of errors detected
during the operation exceeds the threshold provided by
BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biInvoiceImageMinmalRevoke& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images revoked in the bill run operation.  This will always be zero as this function performs a minimal revoke.   
  
[Contents] [Functions]

* * *

### Function  biBillRunInvoiceConsolidateRevoke&

**Declaration**

        
                biBillRunInvoiceConsolidateRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceConsolidateRevoke&.

**Implementation**

Calls biInvoiceConsolidateRevoke& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount unconsolidated from deleted invoices in the currency of the bill run type.  
GENERAL_STATS1 | The number of consolidated invoices deleted as part of this revoke operation.  
GENERAL_STATS2 | The number of statements unconsolidated as part of this revoke operation.  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceUnApply&

**Declaration**

        
                biBillRunInvoiceUnApply&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceUnApply&.

**Implementation**

Calls biInvoiceUnApply& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices unapplied in the bill run operation  
GENERAL_STATS2 | The number of statements unapplied in the bill run operation  
AMOUNT | The total invoice amount unapplied in the bill run operation (including invoices and statements)  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceDeallocate&

**Declaration**

        
                biBillRunInvoiceDeallocate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoiceDeallocate&.

**Implementation**

Calls biInvoiceDeallocateCustomers& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices deallocated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoicePrintRevoke&

**Declaration**

        
                biBillRunInvoicePrintRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoicePrintRevoke&.
biInvoicePrintRevoke& will abort if the number of errors detected during the
operation exceeds the threshold provided by  BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biInvoicePrintRevoke& and sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of images for which printing was revoked in the bill run operation   
  
[Contents] [Functions]

* * *

### Function biBillRunInvoicePrintMinimalRevoke&

**Declaration**

        
                biBillRunInvoicePrintMinimalRevoke&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoicePrintMinmalRevoke&.
biInvoicePrintMinmalRevoke& will abort if the number of errors detected during
the operation exceeds the threshold provided by
BillRunMaxRevokeErrorsPerBatch&.

**Implementation**

Calls biInvoicePrintMinmalRevoke& and sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of images for which printing was revoked in the bill run operation.  This will always be zero as this function performs a minimal revoke.   
  
[Contents] [Functions]

* * *

### Function biBillRunRentalAdjustmentGenerateCorporate&

**Declaration**

        
                biBillRunRentalAdjustmentGenerateCorporate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the RAP interface of
biRentalGenerateCorporate&.

**Implementation**

Calls biRentalGenerateCorporate& with AdjustmentInd& set to TRUE. Sets the
following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalGenerateCorporate&

**Declaration**

        
                biBillRunRentalGenerateCorporate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biRentalGenerateCorporate&.

**Implementation**

Calls biRentalGenerateCorporate& with AdjustmentInd& set to FALSE then sets
the following statistics in the OperationStatistics?{} hash which is used to
populate the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalGenerateCorporate&(2)

**Declaration**

        
                biBillRunRentalGenerateCorporate&(
        	BillRunId&,
           	EffectiveDate~,
           	RentalEffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
RentalEffectiveDate~ | IN: Date-time for rental charge period calculations.  In the variants of this interface without this parameter, the EffectiveDate~ parameter is used to as the Date-time for rental charge period calculations. The variant of this interface with this parameter allows a different date from the bill run Effective Date to be used for rental charge period calculations. This provides a way for bill runs to be performed that have their rentals offset from the usage that is billed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biRentalGenerateCorporate&.

**Implementation**

Calls biRentalGenerateCorporate& with RentalEffectiveDate~ and with
AdjustmentInd& set to FALSE then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceGenerateCorporate&

**Declaration**

        
                biBillRunInvoiceGenerateCorporate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the RAP interface of
biInvoiceGenerateCorporate&.

**Implementation**

Calls biInvoiceGenerateCorporate& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on invoices and statements generated in the bill run operation  
GENERAL_STATS1 | The number of invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements generated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
GENERAL_STATS6 | The number of services that were processed by the bill run operation  
GENERAL_STATS7 | The number of normalised events that were processed by the bill run operation  
GENERAL_STATS9 | The number of original charges that were processed by the bill run operation  
GENERAL_STATS10 | The total number of subtotal and tariff charges generated during the bill run operation  
  
Any customers appearing in SuppressedCustomerNodeList&[] have their invoices
and rentals revoked and the AMOUNT, GENERAL_STATS1, GENERAL_STATS2,
GENERAL_STATS9 and GENERAL_STATS10 statistics adjusted. The total number of
services, events and nodes processed cannot be adjusted so GENERAL_STATS5,
GENERAL_STATS6 and GENERAL_STATS7 are not adjusted.

[Contents] [Functions]

* * *

### Function biBillRunInvoiceImageGenerateCorporate&

**Declaration**

        
                biBillRunInvoiceImageGenerateCorporate&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  FALSE otherwise.

**Description**

Billing Configuration compliant wrapper around
biInvoiceImageGenerateCorporate&.

**Implementation**

Calls biInvoiceImageGenerateCorporate& then sets the following statistics in
the OperationStatistics?{} hash which is used to populate the bill run
operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS3 | The number of invoice images generated in the bill run operation  
GENERAL_STATS4 | The total image size (post-compression) in bytes of all invoice images generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceGenerateHighVolume&

**Declaration**

        
                biBillRunInvoiceGenerateHighVolume&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around biInvoiceGenerateHighVolume&.

**Implementation**

Calls biInvoiceGenerateHighVolume& then sets the following statistics in the
OperationStatistics?{} hash which is used to populate the bill run operation
statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on invoices and statements generated in the bill run operation  
GENERAL_STATS1 | The number of invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements generated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
GENERAL_STATS6 | The number of services that were processed by the bill run operation  
GENERAL_STATS7 | The number of normalised events that were processed by the bill run operation  
GENERAL_STATS9 | The number of original charges that were processed by the bill run operation  
GENERAL_STATS10 | The total number of subtotal and tariff charges generated during the bill run operation  
  
Any customers appearing in SuppressedCustomerNodeList&[] have their invoices
and rentals revoked and the AMOUNT, GENERAL_STATS1, GENERAL_STATS2,
GENERAL_STATS9 and GENERAL_STATS10 statistics adjusted. The total number of
services, events and nodes processed cannot be adjusted so GENERAL_STATS5,
GENERAL_STATS6 and GENERAL_STATS7 are not adjusted.

[Contents] [Functions]

* * *

### Function biBillRunRentalAdjustmentGenerateInterim&

**Declaration**

        
                biBillRunRentalAdjustmentGenerateInterim&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the Interim and RAP interface
of biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to TRUE and InterimInd& set to
TRUE. Sets the following statistics in the OperationStatistics?{} hash which
is used to populate the bill run operation statistics in the
BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunRentalGenerateInterim&

**Declaration**

        
                biBillRunRentalGenerateInterim&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the Interim interface of
biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to FALSE and InterimInd& set
to TRUE. Sets the following statistics in the OperationStatistics?{} hash
which is used to populate the bill run operation statistics in the
BILL_RUN_OPERATION table.

Key | Value  
---|---  
GENERAL_STATS7 | The number of successful events generated in the bill run operation  
GENERAL_STATS8 | The number of error events generated in the bill run operation  
  
[Contents] [Functions]

* * *

### Function biBillRunInvoiceGenerateInterim&

**Declaration**

        
                biBillRunInvoiceGenerateInterim&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the interim interface of
biInvoiceGenerate&.

**Implementation**

Calls biInvoiceGenerate& with InterimInd& set to TRUE then sets the following
statistics in the OperationStatistics?{} parameter which is used to populate
the bill run operation statistics in the BILL_RUN_OPERATION table.

Key | Value  
---|---  
AMOUNT | The total amount billed on invoices and statements generated in the bill run operation  
GENERAL_STATS1 | The number of invoices that were generated by the bill run operation  
GENERAL_STATS2 | The number of statements generated by the bill run operation  
GENERAL_STATS5 | The number of customer nodes that were processed by the bill run operation   
GENERAL_STATS6 | The number of services that were processed by the bill run operation  
GENERAL_STATS7 | The number of normalised events that were processed by the bill run operation  
GENERAL_STATS9 | The number of original charges that were processed by the bill run operation  
GENERAL_STATS10 | The total number of subtotal and tariff charges generated during the bill run operation  
  
Any customers appearing in SuppressedCustomerNodeList&[] have their invoices
and rentals revoked and the AMOUNT, GENERAL_STATS1, GENERAL_STATS2,
GENERAL_STATS9 and GENERAL_STATS10 statistics adjusted. The total number of
services, events and nodes processed cannot be adjusted so GENERAL_STATS5,
GENERAL_STATS6 and GENERAL_STATS7 are not adjusted.

[Contents] [Functions]

* * *

### Function biBillRunRentalAdjustmentGenerateCurrentOnly&

**Declaration**

        
                biBillRunRentalAdjustmentGenerateCurrentOnly&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the Arrears Only interface of
biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to TRUE, MaxPeriodStartDate~
set to an undefined value and CurrentBillRunOnlyInd& set to TRUE. This
function is provided for arrears adjustment on  bill runs dated more than one
bill run cycle in advance. By limiting the adjustments to only the current
bill run events, the adjustment generation is protected against adjusting
events on other "unbilled advance bill runs" with earlier effective dates.

In effect, this function is only required when performing more than one bill
run in advance for arrears rental event generation. If only one advance bill
run is required, or for the earliest advance bill run when multiple are
required, biBillRunRentalAdjustmentGenerate& should be used instead.

[Contents] [Functions]

* * *

### Function biBillRunRentalGenerateArrears&

**Declaration**

        
                biBillRunRentalGenerateArrears&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

TRUE if function completed successfully.  An error is raised otherwise.

**Description**

Billing Configuration compliant wrapper around the Arrears Only interface of
biRentalGenerate&.

**Implementation**

Calls biRentalGenerate& with AdjustmentInd& set to FALSE, MaxPeriodStartDate~
set to EffectiveDate~ and CurrentBillRunOnlyInd& set to FALSE.

[Contents] [Functions]

* * *

### Function biBillRunInvoiceRevokeParallel&

**Declaration**

        
                biBillRunInvoiceRevokeParallel&(
        	BillRunId&,
           	EffectiveDate~,
           	EffectiveDayOfMonth&,
         	BillRunOperationId&,
        	QAInd&,
        	RootCustomerNodeList&[],
        	var SuccessCustomerNodeList&[],
         	var ErrorCustomerNodeList&[],
        	var SuppressedCustomerNodeList&[],
        	var OperationStatistics?{})
        

**Parameters**

BillRunId& | IN:  The unique internal identifier of the bill run to be processed  
---|---  
EffectiveDate~ | IN:  The effective date of the bill run to be processed.  
EffectiveDayOfMonth& | IN: The logical day of the month to associate with EffectiveDate~.   This is normally set to the day of the month of EffectiveDate~. However, if EffectiveDate~ is the last day of the month, then EffectiveDayOfMonth& may be a later day.   
BillRunOperationId& | IN: The unique internal identifier of the bill run operation to be processed  
QAInd& | IN: Indicates if the current bill run is a quality assurance or real bill run. TRUE indicates a quality assurance bill run. FALSE indicates a real bill run  
RootCustomerNodeList&[] | IN:  The list of root customer nodes which must be processed. The list may not be empty.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer nodes that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer ids that were not successfully processed.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer ids that have been suppressed.  
OperationStatistics?{} | OUT: Unknown EPM hash containing the statistics gathered during this bill run operation.  
  
**Returns**

The number of customers successfully processed.  Otherwise an error is raised.

**Description**

Billing Configuration compliant wrapper around biInvoiceRevokeParallel&.

**Implementation**

Calls biInvoiceRevokeParallel& with RevokeParallelConfigItemSeqnr& set to TRUE
then sets the following statistics in the OperationStatistics?{} hash which is
used to populate the bill run operation statistics in the BILL_RUN_OPERATION
table.

Key | Value  
---|---  
GENERAL_STATS1 | The number of invoices deleted in the bill run operation  
GENERAL_STATS2 | The number of statements deleted in the bill run operation  
GENERAL_STATS3 | The number of invoice images deleted in the bill run operation  
GENERAL_STATS9 | The number of charges updated in the bill run operation  
GENERAL_STATS10 | The number of charges deleted in the bill run operation  
AMOUNT | The total amount of all invoices revoked in the bill run operation (including invoices and statements)  
  
[Contents] [Functions]

* * *

###  BillRunMaxRevokeErrorsPerBatch&

**Declaration**

BillRunMaxRevokeErrorsPerBatch&()

**Parameters**

None

**Returns**

The number of errors allowed in a batch revoke operation before it aborts

**Description**

Deterministic function for indicating how many errors are allowed in a batch
revoke operation before the operation aborts. A value of zero returned by this
function indicates that an unlimited amount of errors is allowed. The function
returns 5 by default. This is a BASE_INSTALL function that is able to be
modified by configurers.

**Implementation**

Returns a hard coded number.

[Contents] [Functions]

* * *

### BillRunInvoicePrepaidUsageChargesBeforeBillDate&

**Declaration**

BillRunInvoicePrepaidUsageChargesBeforeBillDate&()

**Parameters**

None

**Returns**

Boolean indicating whether or not to process charges up to but not including
the bill run effective date.

**Description**

Deterministic function. A return value of TRUE means that usage charges prior
to but not including the bill run effective date will be included in the
invoice generation. If set to FALSE, usage charges prior to and including the
bill run effective date will be processed. For example, consider a bill run
with an effective date of 04-AUG-2004 10:00:00. If set to TRUE, usage charges
will be processed up to and including 04-AUG-2004 9:59:59. If set to FALSE,
usage charges on 04-AUG-2004 10:00:00 will also be processed.

This function is analogous to the USAGE_CHARGES_BEFORE_BILL_DATE attribute in
the BGP configuration item.

The function returns FALSE by default. This is a BASE_INSTALL function that is
able to be modified by configurers.

**Implementation**

Returns a hard coded number.

[Contents] [Functions]

* * *

### BillRunInvoicePrepaidMaxErrorsPerBatch&

**Declaration**

BillRunInvoicePrepaidMaxErrorsPerBatch&()

**Parameters**

None

**Returns**

The number of errors allowed in a pre-paid invoice generation operation before
it aborts.

**Description**

Deterministic function for indicating how many errors are allowed in a pre-
paid invoice generation operation before the operation aborts. A value of zero
returned by this function indicates that an unlimited amount of errors is
allowed. The function returns 5 by default. This is a BASE_INSTALL function
that is able to be modified by configurers.

**Implementation**

Returns a hard coded number.

[Contents] [Functions]

* * *

### BillRunZeroAdjustmentType?{}

**Declaration**

BillRunZeroAdjustmentType?{}

**Parameters**

None

**Returns**

A hash of field names and values for zero amount adjustment insertion. The
ADJUSTMENT_TYPE_ID key must be specified.

**Description**

Deterministic function for indicating if a zero value adjustment should be
inserted after bill run invoice allocation by  biInvoiceAllocateCustomers&.
The function returns the adjustment field names and values to insert if there
are both credit and debit receivable types remaining against an account after
bill run invoice allocation. If a non-null value is returned by this function,
a zero value adjustment of the given type is inserted with auto allocation.
With the default allocation algorithms this results in offsetting debits
against credits within and across transactions such that only debits or only
credits remain and there is no net change to the current due.

The function returns null?{} by default. This is a BASE_INSTALL function that
is able to be modified by configurers.

**Implementation**

Returns a hard coded value.

[Contents] [Functions]

* * *

## Bill Run Operation Statistics

A common set of statistics are collected for bill run operations.  A subset of
these are aggregated and displayed as summary statistics for bill runs as
well.  The following table documents the bill run operation statistics that
are supplied with the core CB release, their characteristics, and the
limitations in their calculation and use.   The next section describes the
bill run summary statistics.

In general, statistics for an operation are only available if that operation
completes successfully. If any operation fails, then cumulative statistics for
that operation will not be accurate for operations of that type.  The
exception to this rule is when displaying Net Operation statistics.  In this
case, the Amount, Invoice and Statement statistics will be rederived from
information in the database if there are failed operations associated with the
bill run.   The biBillRunOperationNetSummary&() function is called by the CB
Client to display net operation statistics.



**Bill Run Operation** | **Statistic (Column)** | **Description**  
---|---|---  
10\. Rental Adjustment Event Generation | Events (GENERAL_STATS7) | The number of rental events generated as part of this operation.  
Error Events (GENERAL_STATS8) | The number of rental error events generated as part of this operation.  
20\. Rental Event Generation (RGP) | Events (GENERAL_STATS7) | The number of rental events generated as part of this operation.  
Error Events (GENERAL_STATS8) | The number of rental error events generated as part of this operation.  
30\. Invoice/Statement Generation (BGP) | Amount (AMOUNT) | The amount invoiced in the currency of the bill run type.  
Invoices (GENERAL_STATS1) | The number of invoices generated as part of this operation.  
Statements (GENERAL_STATS2) | The number of statements generated as part of this operation.  
Customer Nodes (GENERAL_STATS5) | The total number of customer nodes processed by the biller as part of this operation.  WARNING:  This statistic is not calculated for revoke operations, and hence when displaying Bill Run Operation Net statistics or Bill Run Summary statistics, this value will not represent the net number of customer nodes that have been processed.  
Services (GENERAL_STATS6) | The total number of services processed by the biller as part of this operation.WARNING:  This statistic is not calculated for revoke operations, and hence when displaying Bill Run Operation Net statistics or Bill Run Summary statistics, this value will not represent the net number of services that have been processed.  
Events (GENERAL_STATS7) | The total number of events processed by the biller as part of this operation.WARNING:  This statistic is not calculated for revoke operations, and hence when displaying Bill Run Operation Net statistics or Bill Run Summary statistics, this value will not represent the net number of events that have been processed.  
Rating Charges (GENERAL_STATS9) | The total number of charges generated by the rater that have been updated by the biller as part of this operation.  This also includes charges generated by the rater associated with rental event generation.  
Billing Charges (GENERAL_STATS10) | The total number of charges inserted by the biller as part of this operation.  This includes both tariff and subtotal charge records.  
35\. Invoice Consolidation | Amount (AMOUNT) | The total amount consolidated from statements into invoices in the currency of the bill run type.  
Invoices (GENERAL_STATS1) | The number of consolidated invoices generated as part of this operation.  
Statements (GENERAL_STATS2) | The number of statements consolidated into invoices as part of this operation.  
Customer Nodes (GENERAL_STATS5) | The total number of customer nodes processed by the biller as part of this operation.  WARNING:  This statistic is not calculated for revoke operations, and hence when displaying Bill Run Operation Net statistics or Bill Run Summary statistics, this value will not represent the net number of customer nodes that have been processed.  
40\. Invoice/Statement Image Generation (IGP) | Images (GENERAL_STATS3) | The number of invoice images generated as part of this operation.  
Stored Images Size (GENERAL_STATS4) | The size of the generated images (in bytes) as stored in the database after any compression has occurred.WARNING:  This statistic is not calculated for revoke operations. Hence when displaying Bill Run Operation Net statistics or Bill Run Summary statistics, this value will not represent the net size of invoice images stored in the database, but the total size of all invoice images generated over the life of the bill run.  
50 - Apply Invoices | Amount (AMOUNT) | The amount of the applied invoices in the currency of the bill run type.  
Invoices (GENERAL_STATS1) | The number of invoices that have been applied as part of this operation.  
60 - Allocate Invoices | Invoices (GENERAL_STATS1) | The number of invoices that have been processed for potential allocation to existing payments and adjustments.  
70 - Print Invoices | Images (GENERAL_STATS3) | The number of invoice images that have been printed as part of this operation.  
  |   |    
138 - Revoke rental events and adjustments | Events (GENERAL_STATS7) | The number of rental events deleted as part of this revoke operation.  
Error Events (GENERAL_STATS8) | The number of rental error events deleted as part of this revoke operation.  
158 - Revoke Invoices/Statements | Invoices (GENERAL_STATS1) | The number of invoices deleted as part of this revoke operation.  
Statements (GENERAL_STATS2) | The number of statements deleted as part of this revoke operation.  
Rating Charges (GENERAL_STATS9) | The number of rating charges that have been updated as part of this revoke operation.  
Billing Charges (GENERAL_STATS10) | The number of billing charges that have been deleted as part of this revoke operation.  
163 - Revoke Invoice Consolidation | Amount (AMOUNT) | The total amount unconsolidated from deleted invoices in the currency of the bill run type.  
Invoices (GENERAL_STATS1) | The number of consolidated invoices deleted as part of this revoke operation.  
Statements (GENERAL_STATS2) | The number of statements unconsolidated as part of this revoke operation.  
168 - Revoke Invoice/Statement Images | Images (GENERAL_STATS3) | The number of invoice images that have been deleted as part of this revoke operation.  
178 - Unapply Invoices | Amount (AMOUNT) | The amount of the invoices that have been unapplied in the currency of the bill run type.  
Invoices (GENERAL_STATS1) | The number of invoices that have been unapplied as part of this revoke operation.  
188 - Unallocate Invoices | Invoices (GENERAL_STATS1) | The number of invoices that have been processed to unallocate them from any payments or adjustments.  
198 - Discard Printing of Invoices | Images (GENERAL_STATS3) | The number of invoice images that have been updated as part of this revoke operation to indicate that they have not been printed.  
  
[Contents]

* * *

## Bill Run Statistics

A subset of the statistics collected for bill run operations are aggregated
and displayed against the bill run.  The set of summary statistics is
configurable based on the bill run type.  The following statistics are
collected for the default bill run types supplied with the core CB release.
These statistics are collected by the biBillRunSummary?{}()  function.



**Statistic (Column)** | **Description**  
---|---  
Amount (AMOUNT) | The net amount invoiced in the currency of the bill run type.  This is obtained from the AMOUNT statistics of the "Invoice/Statement generation", "Revoke Invoices/Statements", "Invoice consolidation" and "Revoke Invoice consolidation" bill run operations.  If any of these operations failed, then the AMOUNT is derived by directly querying the INVOICE table for the bill run.  
Invoices (GENERAL_STATS1) | The net number of invoices that have been generated for this bill run.   This is obtained from the statistics of the "Invoice/Statement generation", "Revoke Invoices/Statements", "Invoice consolidation" and "Revoke Invoice consolidation" bill run operations.  If any of these operations failed, then the AMOUNT is derived by directly querying the INVOICE table for the bill run.  
Statements (GENERAL_STATS2) | The net number of statements that have been generated for this bill run.   This is obtained from the statistics of the "Invoice/Statement generation" and "Revoke Invoices/Statements" bill run operations.  If any of these operations failed, then the AMOUNT is derived by directly querying the INVOICE table for the bill run.  
Images (GENERAL_STATS3) | The net number of invoice images generated for this bill run.  This is obtained from the statistics of the "Invoice/Statement Image generation" and "Revoke Invoice/Statement images" bill run operations.  If any of these operations failed, then this statistic may not accurately reflect the actual number of invoice images that have been generated for this bill run.  
Stored Images Size (GENERAL_STATS4) | The cumulative size of all invoice images generated by the "Invoice/Statement Image Generate" bill run operation.  This includes invoice images that may have been subsequently revoked.  If any "Invoice/Statement Image generation" operations have failed, then this statistic may not be accurate.This statistic does not represent the size of the current invoice images stored in the database for this bill run.   
Customer Nodes (GENERAL_STATS5) | The cumulative number of customer nodes processed by the "Invoice/Statement generation" bill run operation.  This include customer nodes whose invoices or statements may have been subsequently revoked.  If any "Invoice/Statement generation" operations have failed, then this statistic may not be accurate.  
Services (GENERAL_STATS6) | The cumulative number of services processed by the "Invoice/Statement generation" bill run operation.  This includes services whose invoices or statements may have been subsequently revoked.  If any "Invoice/Statement generation" operations have failed, then this statistic may not be accurate.  
Events (GENERAL_STATS7) | The cumulative number of events processed by the "Invoice/Statement generation" bill run operation.  This includes events associated with invoices or statements that may have been subsequently revoked.  If any "Invoice/Statement generation" operations have failed, then this statistic may not be accurate.  
Error Events (GENERAL_STATS8) | The net number of rental and rental adjustment error events for this bill run.  This is obtained from the statistics for the "Rental event generation", "Rental adjustment event generation" and "Revoke rental events and adjustments" bill run operations.  If any of these operations have failed, then this statistic may not be accurate.  
Rating Charges (GENERAL_STATS9) | The net number of rating and rental charges updated by this bill run.   This is obtained from the statistics for the "Invoice/Statement generation" and "Revoke Invoices/Statements" bill run operations. If any of these operations have failed, then this statistic may not be accurate.  
Billing Charges (GENERAL_STATS10) | The net number of billing charges inserted for this bill run.    This is obtained from the statistics for the "Invoice/Statement generation" and "Revoke Invoices/Statements" bill run operations. If any of these operations have failed, then this statistic may not be accurate.  
  
[Contents]

* * *



## Business Rules

There are three class hierarchies involved in implementing the insert, update,
and delete functions.  The first is the Table hierarchy.  The second  is the
Relationship hierarchy, which represents most of the "smarts" of the service.
Finally the Parser hierarchy determines how the relationships work together in
the context of the calling function.  It should be noted that that all parser
and relationship access to the database is via database interfaces classes,
which mirror the parser and relationship hierarchies.

The business rules summary for this service is detailed in the following:

       * Tables
       * Relationships
       * Parsers

[Contents][Business Rules]

* * *

### Tables

Name | **Base Class** | **Unique Fields** | **Key Fields** | **Cascade delete tables**  
---|---|---|---|---  
BILL_RUN | Table | None | BILL_RUN_ID | None  
BILL_RUN_OPERATION | Table | None | BILL_RUN_OPERATION_ID | BILL_RUN  
  
[Contents][Business Rules]

* * *

### Relationships

Relationships determine if the supplied data for an operation is valid.

Relationship Description | Implementation Class  
---|---  
**BILL_RUN** |   
Map the BILL_RUN_TYPE_NAME to the BILL_RUN_TYPE_ID. | NameLookupNonDateRange  
BILL_RUN_TYPE_ID must reference a valid BILL_RUN_TYPE record. | IntegerMatch  
CREATION_TASK_QUEUE_ID must reference a valid TASK_QUEUE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
BILLING_SCHEDULE_ID must reference a valid SCHEDULE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
LAST_TASK_QUEUE_ID must reference a valid TASK_QUEUE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
ATLANTA_OPERATOR_ID must reference a valid ATLANTA_OPERATOR record. | IntegerMatch  
ATLANTA_GROUP_ID must reference a valid ATLANTA_GROUP record. | IntegerMatch  
ERROR_MESSAGE_ID must reference a valid ERROR_MESSAGE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
QA_IND_CODE is defaulted to1 if the QA_IND_CODE is set on the corresponding BILL_RUN_TYPE record. | IntegerDefault  
triggered by a TypelessTrigger  
**UPDATE****only** |   
OPERATOR_ID must have sufficient access privileges to update the BILL_RUN record. | OperatorAccessRel  
**BILL_RUN_OPERATION** |   
BILL_RUN_ID must reference a valid BILL_RUN record. | IntegerMatch  
TASK_QUEUE_ID must reference a valid TASK_QUEUE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
ATLANTA_OPERATOR_ID must reference a valid ATLANTA_OPERATOR record. | IntegerMatch  
ERROR_MESSAGE_ID must reference a valid ERROR_MESSAGE record, if it is not null. | IntegerMatch  
triggered by a TypelessTrigger  
  
[Contents][Business Rules]

* * *

### Parsers

Parsers provide the algorithms for using the relationships.  

Table | **Validate Parser** | **Insert Parser** | **Update Parser** | **Delete Parser**  
---|---|---|---|---  
BILL_RUN | ValidateParser | InsertParser | UpdateParser |    
BILL_RUN_OPERATION | ValidateParser | InsertParser | UpdateParser |    
  
[Contents][Business Rules]

* * *

--------------------------------------------------
## Contents

    Description
    Functions
    Events

* * *

## Related Documents

    Unit Test Plan
    Miscellaneous Allocation Algorithms 

* * *

## Functions

[bi]InvoiceApply& | [bi]InvoiceUnapply&  
---|---  
biInvoiceEventDetailFetch& | biInvoiceEvtOtherDetailFetch&  
[bi]InvoiceFetchById& | [bi]InvoiceFetchByIdx& _\- deprecated_  
biInvoiceHierarchyFetch& | [bi]InvoiceImageFetch&  
biInvoiceImageGenerate$ | [bi]InvoiceImageUpdate&  
[bi]InvoiceQueryFetch& | [bi]InvoiceReceivableTypeFetch&  
[bi]InvoiceSearch& | [bi]InvoiceTransactionFetch&  
biInvoiceTransactionFetch&(2) | [bi]InvoiceUpdate&  
biInvoiceAllocate& | biInvoiceDeallocate&  
biInvoicePrint& | biInvoiceImageRetrieve$  
biInvoiceGenerate& | biInvoiceAllocateCustomers&  
biInvoiceDeallocateCustomers& | biInvoiceRevoke&  
biInvoiceImageRevoke& | biInvoicePrintRevoke&  
biInvoiceImageMinimalRevoke& | biInvoicePrintMinimalRevoke&  
biInvoiceRevokeParallel& | [bi]InvoiceFetchById&(2)  
[bi]InvoiceReportAccounts& | biInvoiceConsolidate&  
biInvoiceConsolidateRevoke& | biInvoicePrepaidGenerate&  
InvoiceHistoryFix&  
  
[Contents]

* * *

### Function [bi]InvoiceApply&

**Declaration**

        
                [bi]InvoiceApply&(BillRunId&,
                        EffectiveDate~,
                        BillRunOperationId&,
                        const RootCustomerNodeList&[],
                        var SuccessCustomerNodeList&[],
                        var ErrorCustomerNodeList&[],
                        var OperationStatistics?{})

**Parameters**

BillRunId& | In:  Internal identifier for the bill run that generated the invoices being applied.  
---|---  
EffectiveDate~ | In:  The effective date of the bill run.  
BillRunOperationId& | In:  The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
RootCustomerNodeList&[] | In:  The list of root customer nodes whose invoices are to be applied.  The list may not be empty.  
SuccessCustomerNodeList&[] | Out:  A list of all root customer ids that were successfully processed.  This list is a subset of the   RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | Out:  A list of root customer nodes for which there were no invoices associated with the given bill run.  
OperationStatistics?{} | Out:  Unknown EPM hash, containing the statistics gathered during the processing of the list of root customers. The statistics structure contains: 
      1. Key: InvoicesApplied  
The number of invoices applied.

      2. Key: AmountApplied  
The total amount applied.  
  
**Returns**

1 if successful. An error is raised otherwise..

**Description**

biInvoiceApply& takes an ordered list of root customer node id's, and for each
root customer, retrieves all the invoices for the specified bill run
associated with all customer nodes, in the specified root customer's
hierarchy, and applies each invoice to its associated account. If all the
invoices for a customer hierarchy have already been applied or the bill run is
a QA Run, an error is raised.

If however, some of the invoices for the customer hierarchy have already been
applied, then once all the unapplied invoices have been applied, a record is
inserted into the CUSTOMER_NODE_BILL_RUN table with a status of success and a
warning message indicating that 'x' invoices in the customer hierarchy were
already applied.  The next root customer node in RootCustomerNodeList&[] is
then processed.

If a customer hierarchy doesn't have an invoice associated with the specified
bill run, then the root customer node id is placed in
ErrorCustomerNodeList&[].   Additionally, a record is inserted into the
CUSTOMER_NODE_BILL_RUN table with a status of failure, and a message
indicating that no invoices associated with the specified bill run were
retrieved for this customer hierarchy.  The next root customer node id in
RootCustomerNodeList&[] is then processed.

Once biInvoiceApply& has retrieved the relevant invoices, each invoice is
processed individually.  The function updates the INVOICE table record for
each invoice to indicate that the invoice has been applied.

_Unless_ the entity being applied is a Statement that is either  pending
consolidation or that has already  been associated with a consolidation
invoice, the associated  ACCOUNT table record is also updated and the
transactions of the account adjusted in the ACCOUNT_HISTORY table to indicate
that an invoice has been applied.

Once all the invoices for the specified customer hierarchy have been applied
successfully,  a record is inserted into the CUSTOMER_NODE_BILL_RUN table,
with a status of success, for the given root customer node, and the root
customer node id is placed in SuccessCustomerNodeList&[].  The next root
customer node in RootCustomerNodeList&[] is then processed.

The accounts associated with each invoice that is processed are passed in an
array to biAccountPurge&() to purge the account cache.

**Implementation**

The "bi" version of this function (ie,  biInvoiceApply&) is implemented as a
remote EPM function which executes in the biBillRunRO service and calls the
local InvoiceApply& function, which is also written in EPM.

The InvoiceApply& function will perform periodic database commits every 10
seconds while processing.  Commit checks are performed following the apply of
each invoice, which means that in the event of an error while processing a
customer, some, but not all, invoices for that hierarchy may be applied.

Before biInvoiceApply& processes a root customer it must first obtain a lock
on the customer to prevent any other billing operation from interfering with
it's processing. Locks are obtained by updating the root customer node's
record in the CUSTOMER_NODE table with the specified bill run operation id and
process id. If these fields are NULL a lock is obtained. After the customer
has been processed, the lock is released (i.e the BILL_RUN_OPERATION_ID, and
PROCESS_IDENTIFIER fields are returned to NULL) to other billing processes.
If a lock is not obtained, or cannot be released for a customer then a record
in inserted into the CUSTOMER_NODE_BILL_RUN table, with a status of failure
and a relevant error message.  Additionally, the root customer node id is
added to the ErrorCustomerNodeId&[].

Once a lock has been obtained, all invoices for the specified bill run, that
are associated with the customer hierarchy are retrieved.   If no invoices
were retrieved then a record is inserted in to the CUSTOMER_NODE_BILL_RUN
table with a status of failure and a relevant error message.  Additionally,
the root customer node id is added to the ErrorCustomerNodeId&[].

The invoices for the specified bill run, that are associated with the given
customer hierarchy, where APPLIED_IND_CODE is not specified are then
retrieved.  If no invoices are retrieved, then all the invoices for the
specified bill run have been applied in this customer hierarchy, and an error
is raised.

The number of invoices retrieved from the previous two queries is then
compared.   If they are not equal, this indicates that some of the invoices
associated with this bill run and customer hierarchy have already been
applied.  In this case, the unapplied invoices are applied,  then a record is
inserted in the CUSTOMER_NODE_BILL_RUN table with a status of success and a
warning message indicating the 'x' invoices in the customer hierarchy have
already been applied.

If the two values are equal, indicating all invoices are still to be applied,
then each invoice is processed individually.  Each invoice has it's record in
the INVOICE table updated with the APPLIED_IND_CODE set to 1 and the
LAST_MODIFIED set to the current date/time.

Once the invoice has been updated in the INVOICE table the account associated
with this invoice is also updated, provided it isn't a Statement that is
either  pending consolidation or that has already been  associated with a
consolidation invoice. This is true (i.e. no account updates required) if
either PENDING_CONSOLIDATION_IND_CODE is 1 or the CONSOLIDATION_INVOICE_ID
isn't NULL, for it's record in the  INVOICE table.

The algorithm for updating the account associated with this invoice is as
follows:

_

    lock the row in the ACCOUNT table for this account (released on commit)

    retrieve from the ACCOUNT_HISTORY table the record for this account as at the issue date of the invoice

    check if future transactions exist for this account; that is, check if the EFFECTIVE_END_DATE of this record is not the sunset date/time (23:59:59 30      Dec 9999)

    if the current balance of this account differs from the balance forward of the invoice then

> if this invoice is a statement then
>
>     if this statement is associated with a liability account and the v8.00
> accounting functionality is enabled then
>
>         calculate new account balance as the current account balance minus
> the STATEMENT_AMOUNT for the invoice
>
>     else
>
>         calculate new account balance as sum of current account balance and
> the STATEMENT_AMOUNT for the invoice
>
>     end if
>
> else
>
>     if this invoice is associated with a liability account and the v8.00
> accounting functionality is enabled then
>
>         calculate new account balance as the current account balance minus
> the INVOICE_AMOUNT for the invoice
>
>     else
>
>         calculate new account balance as sum of current account balance and
> the INVOICE_AMOUNT for the invoice
>
>     end if
>
> end if

    else

> use ACCOUNT_BALANCE from the INVOICE table record for this invoice as the
> new account balance

    end if

    update the retrieved ACCOUNT_HISTORY record by setting the EFFECTIVE_END_DATE to one second prior to the issue date of the invoice

    insert a new ACCOUNT_HISTORY record for this account having:

        CURRENT_BALANCE set to the calculated new account balance  
        INVOICE_ID set to InvoiceId&  
        EFFECTIVE_START_DATE set to the invoice issue date  
        EFFECTIVE_END_DATE set to the sunset date/time  
        APPLIED_DATE set to the current date and time

    if future transactions do not exist for this account then

> update the ACCOUNT table in accordance with the changes made to the
> ACCOUNT_HISTORY table, update the account balance as calculated above, set
> PREVIOUS_INVOICE_ID to the current value of INVOICE_ID, set INVOICE_ID to
> InvoiceId& and subtract from UNBILLED_AMOUNT the UNBILLED_AMOUNT for the
> invoice._
>
> _

    else

> calculate the difference between the previous ACCOUNT_BALANCE and the
> calculated new account balance
>
> update all future transactions by adding this difference to PREVIOUS_BALANCE
> and CURRENT_BALANCE for each relevant ACCOUNT_HISTORY record
>
> increment SEQNR for each ACCOUNT_HISTORY record associated with all future
> transactions
>
> retrieve the IDs of invoices for the last two ACCOUNT_HISTORY records for
> this account
>
> update the ACCOUNT table in accordance with the changes made to the
> ACCOUNT_HISTORY table, update the account balance as calculated above, set
> INVOICE_ID and PREVIOUS_INVOICE_ID accordingly using the invoice IDs
> retrieved in the previous step and subtract from UNBILLED_AMOUNT the
> UNBILLED_AMOUNT for the invoice.

    end if

> if INVOICE_UNBILLED_AMOUNT for this account is _not_ NULL
>

>> _subtract_ from INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT for the invoice

>
> else if INVOICE_ACCOUNT_ID is _not_ NULL
>

>> if the CURRENCY_ID associated with this account does _not_ match the one
associated with INVOICE_ACCOUNT_ID

>>

>>> convert the UNBILLED_AMOUNT of the invoice to the currency of the account
identified by INVOICE_ACCOUNT_ID

>>

>> if the ACCOUNT_CLASS_CODE associated with this account and the
ACCOUNT_CLASS_CODE associated with the account identified by
INVOICE_ACCOUNT_ID are the same, or the v8.00 accounting functionality is
enabled, then

>>

>>> update the ACCOUNT table identified by INVOICE_ACCOUNT_ID by _subtracting_
from INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT (currency converted) for the
invoice

>>>

>>> If BALANCE_FUNCTION_DEFN_ID is not null for the account's ACCOUNT_TYPE
then call the EPM function  zAccountBalanceUpdated& to have it executed and
any additional account updates performed. The INVOICE_ID and the
ACCOUNT_EFFECTIVE_DATE with value ISSUE_DATE are also provided in the
ChangeDetails?{} hash passed to that function.

>>

>> else

>>

>>> update the ACCOUNT table identified by INVOICE_ACCOUNT_ID by _adding_ to
INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT (currency converted) for the
invoice  
>  
>  If BALANCE_FUNCTION_DEFN_ID is not null for the invoice account's
> ACCOUNT_TYPE  then call the EPM function  zAccountBalanceUpdated& to have it
> executed and any additional account updates performed. The INVOICE_ID and
> the ACCOUNT_EFFECTIVE_DATE with value ISSUE_DATE are also provided in the
> ChangeDetails?{} hash passed to that function.
>>

>> end if

>
> end if
>
> if the commit period (10 seconds since last commit) has expired
>
>         Perform a database commit.
>
>         Call __biAccountPurge&__to purge all accounts that have been updated
> in the last transaction.
>
> end if

_

[Contents][Functions]  

* * *

### Function [bi]InvoiceUnapply&

**Declaration**

        
                [bi]InvoiceUnapply&(BillRunId&,
                          EffectiveDate~,
                          BillRunOperationId&,
                          const RootCustomerNodeList&[],
                          var SuccessCustomerNodeList&[],
                          var ErrorCustomerNodeList&[],
                          var OperationStatistics?{})

**Parameters**

BillRunId& | In:  Internal identifier for the bill run that generated the invoices being unapplied.  
---|---  
EffectiveDate~ | In:  The effective date of the bill run.  
BillRunOperationId& | In:  The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
RootCustomerNodeList&[] | In:  The list of root customer nodes whose invoices are to be unapplied.  The list may not be empty.  
SuccessCustomerNodeList&[] | Out:  A list of all root customer ids that were successfully processed.  This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | Out:  A list of root customer nodes for which there were either no invoices or no applied invoices associated with the given bill run.  
OperationStatistics?{} | Out:  Unknown EPM hash, containing the statistics gathered during the processing of the list of root customers. The statistics structure contains: 
      1. Key: InvoicesUnapplied  
The number of invoices unapplied.

      2. Key: AmountUnapplied  
The total amount unapplied.  
  
**Returns**

1 if successful. An error is raised otherwise.

**Description**

biInvoiceUnapply& takes an ordered list of root customer node id's, and for
each root customer, retrieves all the invoices for the specified bill run
associated with all customer nodes, in the specified root customer's
hierarchy, and unapplies each invoice from its associated account.  If the
bill run is a QA Run an error is raised.

If a customer hierarchy has either no invoices or no applied invoices
associated with this bill run, then the root customer node id is placed in
ErrorCustomerNodeList&[].   Additionally, a record is inserted into the
CUSTOMER_NODE_BILL_RUN table with a status of failure, and a message
indicating that no applied invoices associated with the specified bill run
were retrieved for this customer hierarchy.  The next root customer node id in
RootCustomerNodeList&[] is then processed.

If only some of the invoices for the customer hierarchy have been applied,
then once all the applied invoices have been unapplied, a record is inserted
into the CUSTOMER_NODE_BILL_RUN table with a status of success and a warning
message indicating that 'x' invoices in the customer hierarchy were already
unapplied.  The next root customer node in RootCustomerNodeList&[] is then
processed.

If any of the following conditions are satisfied:

      1. a payment has been either partially or completely allocated to the invoice;
      2. an adjustment has been either partially or completely allocated to the invoice;
      3. a dispute has been raised against the invoice;
      4. the account transaction associated with the invoice has been uploaded to the general ledger (GL) system;
      5. part or all of the invoice has been posted to the Sales Journal; or
      6. the invoice is not the most recently applied invoice for its associated account;

then a record is inserted into the CUSTOMER_NODE_BILL_RUN table with a status
of failure and a message indicating why the invoices in this customer
hierarchy cannot be processed, the root customer node id is then placed in
ErrorCustomerNodeList&[].  The next root customer node id in
RootCustomerNodeList&[] is then processed.

Once biInvoiceUnapply& has determined that all the relevant invoices in a
customer hierarchy are valid, each invoice is processed individually.  The
function updates the INVOICE table record for each invoice to indicate that
the invoice has not been applied.  The associated account table record is also
updated to indicated that the invoice has not been applied.  Note: If the
entity being unapplied is a Statement that is either  pending consolidation or
that has already been  associated with a consolidation invoice, then there
won't be any account table records that require reversal. Once all the
invoices for the specified customer hierarchy have been unapplied
successfully,  a record is inserted into the CUSTOMER_NODE_BILL_RUN table for
given root customer node, with a status of success, and the root customer node
id is placed in SuccessCustomerNodeList&[].  The next root customer node id in
RootCustomerNodeList&[] is then processed.

The accounts associated with each invoice that is processed are passed in an
array to biAccountPurge&() to purge the account cache.

**Implementation**

The "bi" version of this function (ie,  biInvoiceUnapply&) is implemented as a
remote EPM function which executes in the biBillRunRO service and calls the
local InvoiceUnapply& function, which is also written in EPM.

The InvoiceUnapply& function will perform periodic database commits every 10
seconds while processing.  Commit checks are performed following the unapply
of each invoice, which means that in the event of an error while processing a
customer, some, but not all, invoices for that hierarchy may be unapplied.

Before biInvoiceUnapply& processes a root customer it must first obtain a lock
on the customer to prevent any other billing operation from interfering with
it's processing. Locks are obtained by updating the root customer node's
record in the CUSTOMER_NODE table with the specified bill run operation id and
process id. If these fields are NULL a lock is obtained. After the customer
has been processed, the lock is released (i.e the BILL_RUN_OPERATION_ID, and
PROCESS_IDENTIFIER fields are returned to NULL) to other billing processes.
If a lock is not obtained, or cannot be released for a customer then a record
in inserted into the CUSTOMER_NODE_BILL_RUN table, with a status of failure
and a relevant error message.  Additionally, the root customer node id is
added to the ErrorCustomerNodeId&[].

Once a lock has been obtained, the number of invoices for the bill run and
customer hierarchy is retrieved. If there are invoices to process, then those
having their APPLIED_IND_CODE set are retrieved. If there are either no
invoices for this customer hierarchy and bill run, or there are invoices but
they are all unapplied i.e. have their APPLIED_IND_CODE already set to NULL,
then this customer hierarchy is treated as errored.

Each retrieved invoice is then validated.  An invoice is deemed invalid for
unapplying if one of the error conditions previously mentioned are satisfied.
If an invoice is determined to be invalid, then the entire customer hierarchy
is skipped, a record is inserted into the CUSTOMER_NODE_BILL_RUN table with a
status of failure and a relevant error message.

Each valid invoice in a customer hierarchy is then processed individually.
Each invoice, has it's record in the INVOICE table updated with the
APPLIED_IND_CODE set to NULL and the LAST_MODIFIED set to the current
date/time.  Once the invoice has been updated in the INVOICE table, the
account associated with this invoice is also updated.

Note: If the entity being unapplied is a Statement that is either  pending
consolidation or that has already been  associated with a consolidation
invoice, then there won't be any account table records that require reversal.
This will be true (i.e. no account reversal required) if either the
PENDING_CONSOLIDATION_IND_CODE is 1 or the CONSOLIDATION_INVOICE_ID isn't
NULL, for it's record in the  INVOICE table.

The algorithm for updating the account associated with this invoice is as
follows:

_

lock the row in the ACCOUNT table for this account (released on commit)

retrieve from the ACCOUNT_HISTORY table the transaction record for this
invoice

the difference to the account balance is calculated to be the previous balance
minus the current balance

if earlier transactions exist for the account associated with this invoice
then

> set the EFFECTIVE_END_DATE of the previous transaction to the
> EFFECTIVE_END_DATE of the transaction associated with this invoice
>
> delete from the ACCOUNT_HISTORY table the transaction record for this
> invoice
>
> update accordingly the balances and sequence numbers of all ACCOUNT_HISTORY
> records for all later transactions

else

> update the current balance and set the INVOICE_ID to null for the
> ACCOUNT_HISTORY record for this invoice
>
> update accordingly the balances of all ACCOUNT_HISTORY records for all later
> transactions

end if

if INVOICE_ACCOUNT_ID is NULL

> if INVOICE_UNBILLED_AMOUNT for this account is _not_ NULL
>

>> _add_ to INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT for the invoice

>
> end if
>
> Update the current ACCOUNT_BALANCE, UNBILLED_AMOUNT, INVOICE_ID,
> PREVIOUS_INVOICE_ID,  INVOICE_UNBILLED_AMOUNT , BALANCE_DATE and
> LAST_MODIFIED for this account
>
> If BALANCE_FUNCTION_DEFN_ID is not null for the account's ACCOUNT_TYPE  then
> call the EPM function  zAccountBalanceUpdated& to have it executed and any
> additional account updates performed. The INVOICE_ID and the
> ACCOUNT_EFFECTIVE_DATE with value ISSUE_DATE are also provided in the
> ChangeDetails?{} hash passed to that function.

else

> Update the current ACCOUNT_BALANCE, UNBILLED_AMOUNT, INVOICE_ID,
> PREVIOUS_INVOICE_ID,   BALANCE_DATE and LAST_MODIFIED for this account
>
> if the CURRENCY_ID associated with this account does _not_ match the one
> associated with INVOICE_ACCOUNT_ID
>

>> convert the UNBILLED_AMOUNT of the invoice to the currency of the account
identified by INVOICE_ACCOUNT_ID

>
> if the ACCOUNT_CLASS_CODE associated with this account and the
> ACCOUNT_CLASS_CODE associated with the account identified by
> INVOICE_ACCOUNT_ID are the same, or the v8.00 accounting functionality is
> enabled, then
>

>> update the ACCOUNT table identified by INVOICE_ACCOUNT_ID by _adding_ to
INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT (currency converted) for the
invoice

>
> else
>

>> update the ACCOUNT table identified by INVOICE_ACCOUNT_ID by _subtracting_
from INVOICE_UNBILLED_AMOUNT the UNBILLED_AMOUNT (currency converted) for the
invoice

>
> end if
>
> If BALANCE_FUNCTION_DEFN_ID is not null for the invoice account's
> ACCOUNT_TYPE  then call the EPM function  zAccountBalanceUpdated& to have it
> executed and any additional account updates performed. The INVOICE_ID and
> the ACCOUNT_EFFECTIVE_DATE with value ISSUE_DATE are also provided in the
> ChangeDetails?{} hash passed to that function.

if the commit period (10 seconds since last commit) has expired

        Perform a database commit

        Call __biAccountPurge&__to purge all accounts that have been updated in the last transaction.

end if

_

[Contents][Functions]  

* * *

### Function biInvoiceEventDetailFetch&

**Declaration**

        
                biInvoiceEventDetailFetch&(WhereClause$,
                                    OrderByClause$
                                    ParamNames$[],
                                    ParamValues?[],
                                    FieldNames$[],
                                    var FieldValues?[])

**Parameters**

WhereClause$ | SQL Where clause.  
---|---  
OrderByClause$ | SQL Order By clause.  
ParamNames$[] | Bind variable names used in WhereClause$.  
ParamValues?[] | Values to bind variable names to.  
FieldNames$[] | Names of the fields from the INVOICE_EVENT_DETAIL_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows; FieldValues?[0][] being the first row retrieved.  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns rows of field values from the INVOICE_EVENT_DETAIL_TRE_V view by
combining the passed information into an SQL select query. The names of the
fields to retrieve are passed in FieldNames$[] and their values are returned
in the two dimensional array FieldValues?[].

INVOICE_EVENT_DETAIL_TRE_V defines the set of valid field names. An error is
raised if invalid field names are requested.

**Implementation**

This function was implemented as a remote EPM (Expression Parser Module)
function and uses biSQLQueryx.

[Contents][Functions]  

* * *

### Function biInvoiceEvtOtherDetailFetch&

**Declaration**

        
                biInvoiceEvtOtherDetailFetch&(WhereClause$,
                                      OrderByClause$
                                      ParamNames$[],
                                      ParamValues?[],
                                      FieldNames$[],
                                      var FieldValues?[])

**Parameters**

WhereClause$ | SQL Where clause.  
---|---  
OrderByClause$ | SQL Order By clause.  
ParamNames$[] | Bind variable names used in WhereClause$.  
ParamValues?[] | Values to bind variable names to.  
FieldNames$[] | Names of the fields from the INVOICE_OTHER_DETAIL_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows; FieldValues?[0][] being the first row retrieved.  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns rows of field values from the INVOICE_OTHER_DETAIL_TRE_V view by
combining the passed information into an SQL select query. The names of the
fields to retrieve are passed in FieldNames$[] and their values are returned
in the two dimensional array FieldValues?[].

INVOICE_OTHER_DETAIL_TRE_V defines the set of valid field names. An error is
raised if invalid field names are requested

**Implementation**

This function was implemented as a remote EPM (Expression Parser Module)
function and uses biSQLQueryx.

[Contents][Functions]  

* * *

### Function [bi]InvoiceFetchById&

**Declaration**

        
                [bi]InvoiceFetchById&(InvoiceId&,
                              const FieldNames$[],
                              var StringFieldValues$[],
                              var IntegerFieldValues&[],
                              var RealFieldValues#[],
                              var DateFieldValues~[]) 

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_TRE_V view whose values are to be returned.  These must be specified in order of data type, the order being string fields first followed by integer fields, real fields and finally date fields.  
StringFieldValues$[] | Out: String field values for the fetched row.  
IntegerFieldValues&[] | Out: Integer field values for the fetched row.  
RealFieldValues#[] | Out: Real field values for the fetched row.  
DateFieldValues~[] | Out: Date field values for the fetched row.  
  
**Returns**

Returns 1 if successful, 0 if no record found.  An error is raised if invalid
field names are requested.

**Description**

Returns a single row of field values from the INVOICE_TRE_V view by performing
a query on InvoiceId&. The names of the fields to retrieve are passed in
FieldNames$[] and their values are returned in the array corresponding to
their particular data type.

INVOICE_TRE_V defines the set of valid field names.

**Implementation**

The "bi" version of this function (ie, biInvoiceFetchById&) is implemented as
a wrapper around the InvoiceFetchById& EPM callback function.  The
InvoiceFetchById& function is  implemented using the FetchByIdFuncNDR class by
direct instantiation.

[Contents][Functions]  

* * *

### Function [bi]InvoiceFetchById&(2);

**Declaration**

        
                [bi]InvoiceFetchById&(InvoiceId&,
                              const FieldNames$[],
                              var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Field values fetched.  
  
**Returns**

Returns 1 if successful, 0 if no record found.  An error is raised if invalid
field names are requested.

**Description**

Returns a single row of field values from the INVOICE_TRE_V view by performing
a query on InvoiceId&. The names of the fields to retrieve are passed in
FieldNames$[] and their values are returned in the unknown array
FieldValues?[].

INVOICE_TRE_V defines the set of valid field names.

**Implementation**

The "bi" version of this function (ie, biInvoiceFetchByIdx&) is implemented as
a wrapper around the InvoiceFetchByIdx& EPM callback function.
InvoiceFetchByIdx& is implemented using the FetchByIdFuncNDRx class.

[Contents][Functions]

* * *

### Function [bi]InvoiceFetchByIdx&

**Declaration**

        
                [bi]InvoiceFetchByIdx&(InvoiceId&,
                               const FieldNames$[],
                               var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Field values fetched.  
  
**Returns**

Returns 1 if successful, 0 if no record found.  An error is raised if invalid
field names are requested.

**Description**

This is a deprecated function and exists for backwards compatibility, use
biInvoiceFetchById&(2) instead.

Returns a single row of field values from the INVOICE_TRE_V view by performing
a query on InvoiceId&. The names of the fields to retrieve are passed in
FieldNames$[] and their values are returned in the unknown array
FieldValues?[].

INVOICE_TRE_V defines the set of valid field names.

**Implementation**

The "bi" version of this function (ie, biInvoiceFetchByIdx&) is implemented as
a wrapper around the InvoiceFetchByIdx& EPM callback function.
InvoiceFetchByIdx& is implemented using the FetchByIdFuncNDRx class.

[Contents][Functions]

* * *

### Function biInvoiceHierarchyFetch&

**Declaration**

        
                biInvoiceHierarchyFetch&(InvoiceId&,
                                 ParentCustNodeId&,
                                 ParentServiceId&,
                                 FilterNodeName$,
                                 FilterServiceNumber$,
                                 FilterServiceType&,
                                 FilterNEType&,
                                 CountWhereClauseCust$,
                                 CountWhereClauseSvc$,
                                 CountWhereClauseNE$,
                                 CountParamNamesCust$[],
                                 CountParamValuesCust?[],
                                 CountParamNamesSvc$[],
                                 CountParamValuesSvc?[],
                                 CountParamNamesNE$[],
                                 CountParamValuesNE?[],
                                 Flags&,
                                 var FieldValues?[])

**Parameters**

InvoiceId& | Internal Id of the invoice on which to perform the fetch.  
---|---  
ParentCustNodeId& | If in Auto-Expand mode, parent customer node for which to retrieve immediate children. Only effective if Auto-Expand flag set.  
ParentServiceId& | If in Auto-Expand mode, parent service for which to retrieve immediate children. Only effective if Auto-Expand flag set.  
FilterNodeName$ | Customer node name filtering criteria.  Only effective if filter flag set.  
FilterServiceNumber$ | Service name filtering criteria.  Only effective if filter flag set.  
FilterServiceType& | Service type filtering criteria.  Only effective if filter flag set.  
FilterNEType& | Normalised event type filtering criteria.  Only effective if filter flag set.  
CountWhereClauseCust$ | Additional where clause component generated from filtering criteria that effect _customer node level_ invoice item details.  Used when trimming the hierarchy to a minimum for the given filtering criteria, and for obtaining a count for each customer node entity, as required.  
This where clause operates on INVOICE_OTHER_DETAIL_TRE_V..  _Aliasing is
required to "iodtv"._  
Filtering only effective if filter flag set.  Count only performed if count
flag set.  
CountWhereClauseSvc$ | Additional where clause component generated from filtering criteria that effect _service level_ invoice item details.  Used when trimming the hierarchy to a minimum for the given filtering criteria, and for obtaining a count for each service entity, as required.  
This where clause operates on INVOICE_OTHER_DETAIL_TRE_V..  _Aliasing is
required to "iodtv"._  
Filtering only effective if filter flag set.  Count only performed if count
flag set.  
CountWhereClauseNE$ | Additional where clause component generated from filtering criteria that effect _normalised event_ level invoice item details.  Used when trimming the hierarchy to a minimum for the given filtering criteria, and for obtaining a count for each normalised event entity, as required.  
This where clause operates on INVOICE_EVENT_DETAIL_TRE_V..  _Aliasing is
required to "iedtv"._  
Filtering only effective if filter flag set.  Count only performed if count
flag set.  
CountParamNamesCust$[] | Bind variable names used in CountWhereClauseCust$.  Ensure uniqueness in bind variable names between these three where clauses.  
CountParamValuesCust?[] | Values to bind variables names to, in CountWhereClauseCust$.  
CountParamNamesSvc$[] | Bind variable names used in CountWhereClauseSvc$.  Ensure uniqueness in bind variable names between these three where clauses.  
CountParamValuesSvc?[] | Values to bind variables names to, in CountWhereClauseSvc$.  
CountParamNamesNE$[] | Bind variable names used in CountWhereClauseNE$.  Ensure uniqueness in bind variable names between these three where clauses.  
CountParamValuesNE?[] | Values to bind variables names to, in CountWhereClauseNE$.  
Flags& | Bitwise set of flags.  
Bit 0 - Perform a count.  
Bit 1 - Ignore DONT_DISPLAY_IND_CODE when performing a count.  
Bit 2 - Apply filtering.  
Bit 3 - Delete un-matching entities.  Default is to flag them for later
deletion by the calling client.  
Bit 4 - Auto Expand mode.  
Bit 5 - Auto Expand mode, prime customer node.  
FieldValues?[] | Result Set.  
Contains a hierarchy representing all customers, services, and normalised
event types matching both the invoice id and the given where clauses.  See
Description section for a more detailed explanation of its construction.  
  
**Returns**

1 if successful.

0 if no invoice/statement record found.

**Description**

For a given Invoice Id, this function returns a hierarchy of all customers,
services and normalised event types belonging to that invoice.  The entities
returned may be filtered by specifying filtering criteria in FilterNodeName$,
FilterServiceNumber$, FilterServiceType&, FilterNEType&,
CountWhereClauseCust$, CountWhereClauseSvc$, and CountWhereClauseNE$.

Depending on the state of the auto-expand flags, either the whole invoice
hierarchy is returned (full retrieval mode), or only immediate children are
returned (auto-expand mode).  This facility has been introduced due to
performance implications involved in retrieving large hierarchies.

Three different possibilities exist for retrieving immediate children while
operating in Auto-Expand mode.  "Auto Expand mode" flag must be set for all.

>        * Prime customer node: First retrieval as user is expanding into a
> hierarchy.   "Auto Expand mode, prime customer node" flag must be set.
>        * Non-prime customer node: Second and all subsequent retrievals as
> user expands into a hierarchy.  ParentCustNodeId& must be supplied, and
> ParentServiceId& must be null.
>        * Service node:  Expanding any service node to display all child
> Normaliseed Event types for that service.  Both ParentCustNodeId& and
> ParentServiceId& must be supplied.

When filtering is performed, those entities not required to allow a drill down
to all matches will be flagged for removal.  Optionally, these flagged
entities may be deleted.

If the filter flag is set, filtering criteria will be applied.  If the filter
flag is not set, any filtering criteria specified in the filter parameters
will be ignored.

If the delete flag is set, and filtering is performed, unmatching hierarchy
entries with no matching child entries, will be removed from the hierarchy.
Otherwise, each row is flagged as a non-match, and it becomes the calling
clients responsibility to remove the unmatching entities.

The hierarchy returned can be filtered in any combination of five filtering
methods.   When filtering criteria is entered, entities matching that
filtering criteria, or required to return child entities matching that
criteria, are kept.  All other nodes are deleted, or flagged for deletion, as
described earlier.

The five filtering methods are:

       * _Customer Node Name   _            (FilterNodeName$)
       * _Service Number_                         (FilterServiceNumber$)
       * _Service Type_                              (FilterServiceType&)
       * _Normalised Event Type_             (FilterNEType&)
       * _Detail Match_                              (CountWhereClauseCust$ or CountWhereClauseSvc$ or CountWhereClauseNE$).
         * This filtering method combines those criteria that do not apply directly to the hierarchy details, but rather to the invoice item details for each entity in the hierarchy.

These methods are considered "AND" conditions, such that if more than one
method is specified, entities must match all given filtering criteria to be
returned.   For example, if FilterNodeName$ and FilterServiceNumber$ are both
populated, then Customer Node entities returned must match the node name, and
have a child service matching the Service Number to be populated.  Service
entities must match the Service Number.  It is implied that the service must
match the node name condition also, since the parent customer (and hence all
child services) will be removed if it does not match.  All child Normalised
Event Types for matching services will be returned, in this case.

The _Detail Match_ filter method operates differently, but is still considered
an "AND" condition with respect to the other filtering methods.  However, each
of the three where clauses are "OR" conditions with respect to each other,
such that if any matches are found using the three where clauses, the Detail
Match is satisfied.  The three filtering criteria that make up the Detail
Match must be pre-constructed where clauses, with valid aliasing and column
names, as described in the Parameters Section, whereas FilterNodeName$,
FilterServiceNumber$, FilterServiceType&, and FilterNEType& contain the raw
values to match.

If any of CountWhereClauseCust$, CountWhereClauseSvc$, or CountWhereClauseNE$
are populated, the filtering is as follows:  For a Customer Node entity, the
Detail Match filter checks that the node contains invoice items matching the
filtering specified in CountWhereClauseCust$, or has child services containing
invoice items matching CountWhereClauseSvc$, or has child services with child
Normalised Event Types matching CountWhereClauseNE$.  For a Service entity,
the Detail Match filter performs the same check as for a customer node, only
starting at the service level.  For a Normalised Event Type entity, only the
normalised event type check is performed.  If any of these three conditions
are found, the node in question is deemed having Detail Matches.   It should
be noted that this result must still be ANDed to any matches from any of the
other filtering methods, if any were specified.

For example, if FilterNodeName$ and CountWhereClauseSvc$ are both specified,
matching customer nodes must match FilterNodeName$, and must also contain
child services with invoice items matching the conditions described in
CountWhereClauseSvc$.

Assuming all filtering methods are specified, an entity will match using the
following outline:

Node Name  
AND  
Service Number  
AND  
Service Type  
AND  
Normalised Event Type  
AND  
Detail Matches

Where a Detail Match is defined as:

CountWhereClauseCust$  
or  
CountWhereClauseSvc$  
or  
CountWhereClauseNE$

If a count is required and the count flag set, the performed count can be
ensured accurate by populating CountWhereClauseCust$, CountWhereClauseSvc$,
and CountWhereClauseNE$.   This ensures the SQL used to extract the count is
identical to the SQL used to extract invoice item details by the calling form.

The format for the hierarchy, as returned in FieldValues?[], is as follows:

FieldValues?[0] - Entity Type.  (0 - Customer;  1 - Service;  2 - NE Type)  
FieldValues?[1] - Entity Id  
FieldValues?[2] - Entity Name  
FieldValues?[3] - Icon Id  
FieldValues?[4] - Count  
FieldValues?[5] - Invoice Id this child belongs to.  
FieldValues?[6] - Delete Flag.  
FieldValues?[7] - First child details  
    FieldValues?[7][0] - Entity Type (0 - Customer;  1 - Service;  2 - NE Type)  
    FieldValues?[7][1] - Entity Id  
    FieldValues?[7][2] - Entity Name  
    FieldValues?[7][3] - Icon Id  
    FieldValues?[7][4] - Count  
    FieldValues?[7][5] - Invoice Id this child belongs to.  
    FieldValues?[7][6] - Delete Flag.  
    FieldValues?[7][7] - First child details  
        FieldValues?[7][7][0] - Entity Type    _... and so on ..._  
    FieldValues?[7][8] - Second child details  
        FieldValues?[7][8][0] - Entity Type    _... and so on ..._  
FieldValues?[8] - Second child details  
    FieldValues?[8][0] - Entity Type _... and so on ..._

The first entity in the hierarchy is always the prime customer node, who is
responsible for the invoice or statement.   If the invoice has no child
customers or services, then FieldValues?[7] will be null.  Otherwise,
FieldValues?[7] will contain the first child, which itself can contain further
children, as illustrated.

A hierarchy is constructed of entites, of type customer (0), service (1), and
normalised event (2) type.  Customer entities can contain child customer
entites and service entities, with customers appearing first.  Service
entities can contain only child normalised event type entities.

Ordering of the information returned will be as follows:

The customer node responsible for the invoice is inserted as the first entity
in FieldValues?[].

Any child customers of the prime customers are ordered alphabetically by
NODE_NAME, and are each inserted as elements in the array.  Each of these
customers contains their child customers and services, in a recursive manner
using the same format as the main customer node.

Any services belonging to the customer node are ordered alphabetically by
SERVICE_NAME, and are each inserted as elements in the array, following any
child customers that have already been inserted.

The normalised event types of any normalised events for each service are
ordered alphabetically by NORMALISED_EVENT_TYPE_NAME, and are inserted as
children of the appropriate service.

_  
Consolidated Invoices_

The individual invoice statements that comprise a consolidation invoice are
returned in the hierarchy immediately below the prime customer node entity.
These records are identical to child customer records, except that the Invoice
Id listed will be that of the consolidated statement, not the containing
invoice.  The Entity Id will be the customer node id of the prime customer
node for the statement, which may or may not match the containing invoice's.
A separate entity is returned for each statement, regardless of whether they
share the same prime customer node id or not.  The Entity Name will contain
the customer node name with the statement's customer invoice string appended
in brackets.  Alternative - if set in via the Flags& (see below) - the invoice
string will be concatenated in front of the customer node name and separated
by four pipes ('||||').  The later is provided to simplify programmatic
separation of the two strings.  
Each statement's prime customer may contain further child entity's, as per any
other customer entity in the hierarchy, although the Invoice Id in each case
will correspond to the statement's.

Note, when using auto-expand with repeated calls to this function to retrieve
nodes below a consolidated statement,  always pass the statement's Invoice Id,
not the consolidation invoice's.



**Implementation**

This function was implemented as a remote EPM (Expression Parser Module)
function.

biInvoiceHierarchyFetch& extracts details of the prime customer node for the
invoice, then calls the following functions.

zbiRetrieveCustHierarchy?[] retrieves all child customer details into a
2-dimensional array.  If the filter flag is set, a second array of matching
child customers is retrieved, using the given filtering criteria.  Any nodes
from the first array, not matching, or having matching nodes as children, are
flagged for later deletion.  If the delete flag is set, any flagged nodes are
removed.  Finally, the 2-dimensional array is converted to a hierarchy
structure, as outlined in the description section.   During this conversion,
zbiRetrieveServiceHierarchy?[] is called to retrieve service and normalised
event type details for each customer node.

zbiRetrieveServiceHierarchy?[] is called by biInvoiceHierarchyFetch& (for the
prime customer node), and again for each customer node retrieved by
zbiRetrieveCustHierarchy?[].   It returns details of all services belonging to
the given customer node, which are attached to the end of that customer node's
child records in the hierarchy structure.   For each service, the normalised
event types of any normalised events belong to the customer, are attached as
children of each service.  Note that normalised event types must have valid
entity validation to allow their display on the client, to be returned.

zbiRetrieveEntityCount& performs a count of all matching item details for a
given entity.  If the Ignore DONT_DISPLAY_IND_CODE flag is set, then hidden
tariffs and subtotals will be counted.

Searching for customers, services, and normalised event types involves
executing three separate SQL statements.  When filtering is required, SQL
where clauses are constructed, using FilterNodeName$, FilterServiceNumber$,
FilterServiceType&, and FilterNEType&.  These parameters contain the bare
values, and are manipulated into the correct where clause format.  The
construction of where clauses to achieve this filtering is handled internally
by the function.  However, when detail filtering is required, three correctly
formatted and constructed where clauses must be passed to the function.

When constructing detail (or "count") where clauses for customer node,
service, or normalised event entities, no leading "AND" is required, and valid
column names from the correct view must be used.

The views used by these where clauses are:  
    Customer node entities:         INVOICE_OTHER_DETAIL_TRE_V.   Aliasing is required to "iodtv".  
    Service entities:                     INVOICE_OTHER_DETAIL_TRE_V.   Aliasing is required to "iodtv".  
    Normalised event entities:     INVOICE_EVENT_DETAIL_TRE_V.   Aliasing is required  to "iedtv".  

Flags& contains a bitwise set of flags.  
Bit 0 - Perform a count.  
Bit 1 - Ignore DONT_DISPLAY_IND_CODE when performing a count.  
Bit 2 - Apply filtering.  
Bit 3 - Delete un-matching entities.  Default is to flag them for later
deletion by the calling client.  
Bit 4 - Operate in Auto-Expand mode.  
Bit 5 - When in Auto-Expand mode, retrieve details of Prime Customer Node
only.  
Bit 6 - When dealing with consolidation invoices, set the entity name for the
statement's prime customer entity to "Invoice String||||Customer Node Name" as
opposed to the more reader friendly "Customer Node Name (Invoice String)".

Normalised event types do not have icons associated with them.  However,
within the Configuation Explorer , a icon is defined in the base install
group, that is used for all normalised event types the Configuration Explorer
displays.  This icon is also used by this function when displaying normalised
event types.  The icon id for this icon is hard coded as the icon id for _all_
normalised event types.

Each of the epm Expression Parser Module functions are extensively commented.
Further implementation information can be found by inspecting the function
body for each of these functions.

If Auto-Expand mode is being used to retrieve the details of a Prime Customer
Node or if non-auto-expand mode is used (i.e. return entire hierarchy), the
invoice id is checked via a query to see if it is a consolidation invoice.  If
so, each consolidated invoice and its corresponding prime customer node is
retrieved.   For each one, biInvoiceHierarchyFetch& calls itself recursively
passing the consolidated child invoice and customer node id, but leaving all
other parameters the same.  The data returned from each call is appended to
FieldValues?[] as a child record (not a sibling).  The name of the top
customer node returned for each statement is adjusted to include the invoice
string in the format mandated by bit 6 in the Flags&.

[Contents][Functions]  

* * *

### Function [bi]InvoiceImageFetch&

**Declaration**

        
                [bi]InvoiceImageFetch&(InvoiceId&,
                               const FieldNames$[],
                               var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_IMAGE_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows; FieldValues?[0][] being the first row retrieved.  
The order will be by SEQNR ascending.  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns rows of field values from the INVOICE_IMAGE_TRE_V view by performing a
query on InvoiceId&. The names of the fields to retrieve are passed in
FieldNames$[] and their values are returned in the two dimensional array
FieldValues?[].

INVOICE_IMAGE_TRE_V defines the set of valid field names. An error is raised
if invalid field names are requested.

Returns 1 if successful, 0 if no record found.

**Implementation**

The "bi" version of this function (ie, biInvoiceImageFetch&) is implemented as
a wrapper around the InvoiceImageFetch& EPM callback function.
InvoiceImageFetch& is implemented using the FetchDetailFuncNDRx class.

SEQNR is passed as the order by clause parameter to the FetchDetailFuncNDRx
constructor.

[Contents][Functions]  

* * *

### Function biInvoiceImageRetrieve$

**Declaration**

        
                biInvoiceImageRetrieve$(InvoiceId&,
                                Seqnr&,
                                ImageType$,
        		        WorkStation$,
        		        Regenerate&,
        		        var CachedCopy&)
        **Parameters**

InvoiceId& | Unique identifier of invoice whose image is required  
---|---  
Seqnr& | Identifiers particular image (format, etc) required for invoice  
ImageType$ | The type of image to be generated (eg. 'pdf')  
WorkStation$ | Workstation requesting this image  
Regenerate& | If TRUE (non_zero), ignore cached image (if it exists) and re-generate it.  
CachedCopy& | Output only: Sets to TRUE (non_zero) if a cached copy was found and was retruned.   Sets to FALSE (0) if the image was (re)generated.  Always FALSE (=0) if Regenerate& = TRUE (non_zero)  
  
**Returns**

The file name of the generated image prefixed by the value of the
CALLER_PREFIX configuration attribute.

**Description**

If the image already exists in the default location specified in the
configuration item INVOICE_IMAGE and Regenerate& is FALSE, this function
returns a reference to the image and sets CachedCopy& to TRUE.  If no such an
image exists or Regenerate& is TRUE, it generates an image for the specified
file name <InvoiceId&>_<Seqnr&>.<ImageType$>,  and sets CachedCopy& to FALSE.

If no invoice image exists in the database for the specified InvoiceId& and
Seqnr& then an error is raised.

The image type stored in the INVOICE_CONTENTS table is specified by the
STORED_IMAGE_TYPE_CODE field, which maps to an invoice type listed in the
OUTPUT_IMAGE_TYPE reference type. If ImageType$ is not specified, this
function uses the DisplayImageType Derived Attribute Table, which maps each
OUTPUT_IMAGE_TYPE reference type to a desired DISPLAY_IMAGE_TYPE reference
type, to produce an image viewable by the client (eg pdf, ps, dvi, etc). This
allows the client then to view multiple image types for the same invoice
(without the need for any client modifications). If the attribute table does
not contain a mapping for the required OUTPUT_IMAGE_TYPE, error E06400 is
raised.

The ivp (-n option) is called to generate the image. Prior to calling the ivp
and after determining the required Display Image Type, this function performs
a lookup on the DisplayImageMethod derived attribute table using an Entity
Image Type of "Invoice", the Output Image Type retrieved from the
INVOICE_CONTENTS table and the required Display Image Type. If a row is found
the associated Script Name will be passed to the ivp via its -script command
line option. This will be used by the ivp to generate the image instead of its
default behaviour of invoking the view_inv_<display_image_type> script.

The configuration item INVOICE_IMAGE has three attributes:  
    CACHE_DIRECTORY - The server directory in which generated files are located.  
    CALLER_PREFIX - A prefix to the generated file which identifies the access mechanism and location of the file to the caller of this function.   
    INSTANCE - The Convergent Billing Instance on which this process is to be run.

In the clustered environment, the proper configuration item INVOICE_IMAGE will
be chosen based on the CB instance on which the request is being processed at
that time.

  
The generated image file is stored into the default location specified in the
configuration item. The image file name is <InvoiceId&>_<Seqnr&>.<ImageType$>.  
  
The WorkStation$ is ignored by this EPM function.  
  
This function is in the BASE_INSTALL group and hence can be modified by
configuration teams and/or clients.

**Implementation**

This function is implemented as a remote EPM function.

[Contents][Functions]  

* * *

### Function [bi]InvoiceImageUpdate&

**Declaration**

        
                [bi]InvoiceImageUpdate&(InvoiceId&,
                                var LastModified~,
                                const Opcode&[],
                                const Seqnr&[],
                                const FieldNames$[],
                                const FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the update.  
---|---  
LastModified& | The current last modified date and time of the INVOICE record identified by InvoiceId&.  
OUT: The new last modified date and time.  
Opcode&[] | The operation to perform on each row in FieldValues?[]. Only an update (2) operation is allowed.  
Seqnr&[] | Sequence numbers identifying the specific invoice images to operate on.  
FieldNames$[] | Names of the fields from the view INVOICE_IMAGE_TRE_V whose values are to be updated.  
FieldValues?[] | Two dimensional array of new row field values; FieldValues?[0][] being the first row.  
  
**Returns**

Returns the number of processed rows if successful. Raises an error otherwise.

**Description**

Updates invoice images details. _Only theINVOICE_IMAGE_TRE_V.REPRINT_IND_CODE
field may be updated._

**Implementation**

The "bi" version of this function (ie, biInvoiceImageUpdate&) is implemented
as a wrapper around the InvoiceImageUpdate& EPM callback function.
InvoiceImageUpdate& is implemented by the InvoiceImageUpdateFunc class which
is derived from the ArrayUpdateSeqFuncNDRx class.

Here is a description of the overridden methods.

PrepareArgs()

    Extracts the FieldNames$[] parameter in addition to the parameters from the base class.
DumpArgs()

    Call the base DumpArgs().  
Print the FieldNames$[] array.

PrepareSql()

    Call the base PrepareSql().
    Disallow any row operation other than an update.
SetRowValidator()

    Use the SVC's ArrayRowValByTable row validator since this function interface accepts an array of field names.

The InvoiceDb class is derived from the RDB Database class to override the
CreateRules() method.  An instance of the INVOICE_CONTENTS table class is
instantiated in CreateRules() and all fields other than REPRINT_IND_CODE are
disallowed for update.

[Contents][Functions]  

* * *

### Function [bi]InvoiceQueryFetch&

**Declaration**

        
                [bi]InvoiceQueryFetch&(InvoiceId&,
                               const FieldNames$[],
                               var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_QUERY_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows; FieldValues?[0][] being the first row retrieved.  
The order will be by QUERY_NR ascending.  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns rows of field values from the INVOICE_QUERY_TRE_V view by performing a
query on InvoiceId&. The names of the fields to retrieve are passed in
FieldNames$[] and their values are returned in the two dimensional array
FieldValues?[].

INVOICE_QUERY_TRE_V defines the set of valid field names. An error is raised
if invalid field names are requested.

Returns 1 if successful, 0 if no record found.

**Implementation**

This function was implemented using the FetchDetailFuncNDRx class.

QUERY_NR is passed as the order by clause parameter to the FetchDetailFuncNDRx
constructor.

[Contents][Functions]  

* * *

### Function [bi]InvoiceReceivableTypeFetch&

**Declaration**

        
                [bi]InvoiceReceivableTypeFetch&(InvoiceId&,
                                        const FieldNames$[],
                                        var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_RECTYPE_TRE_V view whose values are to be returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows; FieldValues?[0][] being the first row retrieved.  
The order will be by RECEIVABLE_TYPE_NAME.  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns multiple rows of field values from the INVOICE_RECTYPE_TRE_V view by
performing a query on InvoiceId&. The names of the fields to retrieve are
passed in FieldNames$[] and their values are returned in the two dimensional
array FieldValues?[].

INVOICE_RECTYPE_TRE_V defines the set of valid field names. An error is raised
if invalid field names are requested.

**Implementation**

The "bi" version of this function (ie, biInvoiceReceivableTypeFetch&) is
implemented as a wrapper around the InvoiceReceivableTypeFetch& EPM callback
function.   InvoiceReceivableTypeFetch& is  implemented using the
FetchDetailFuncNDRx class by direct instantiation.

RECEIVABLE_TYPE_NAME is passed as the order by clause parameter to the
FetchDetailFuncNDRx constructor.

[Contents][Functions]  

* * *

### Function [bi]InvoiceSearch&

**Declaration**

        
                [bi]InvoiceSearch&(WhereClause$,
                           OrderByClause$,
                           var InvoiceId&[],
                           var LastModified~[])

**Parameters**

WhereClause$ | SQL Where clause.  
---|---  
OrderByClause$ | SQL Order By clause.  
var InvoiceId&[] | OUT: Array of matched invoice Ids.  
var LastModified~[] | OUT: Array of last modified date and time field values, one for each matched invoice Id.  
  
**Returns**

The number of matched invoices.  Raises an error if a buffer overflow occurs.

**Description**

Performs a search on INVOICE_TRE_V.

Returns number of matches found, with matching INVOICE_ID and LAST_MODIFIED
values returned in the InvoiceId&[] and LastModified~[] arrays respectively.

**Implementation**

The "bi" version of this function (ie, biInvoiceSearch&) is implemented as a
wrapper around the InvoiceSearch& EPM callback function.  InvoiceSearch& iss
implemented using the SearchFuncNDR class (a non daterange version of the
SearchFunc class).

[Contents][Functions]

* * *

### Function [bi]InvoiceTransactionFetch&

**Declaration**

        
                [bi]InvoiceTransactionFetch&(InvoiceId&,
                                     const FieldNames$[],
                                     var FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_TRANSACTION_TRE_V view whose values are to be returned.  If this array is empty then all fields are returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows, FieldValues?[0][] being the first row retrieved.  
The rows are ordered by NVL(ADJUSTMENT_DATE, PAYMENT_DATE).  
  
**Returns**

The number of rows in FieldValues?[] if successful, 0 if no record found.

**Description**

Returns rows of field values from the INVOICE_TRANSACTION_TRE_V view by
performing a query on InvoiceId&. The names of the fields to retrieve are
passed in FieldNames$[] and their values are returned in the two dimensional
array FieldValues?[].

INVOICE_TRANSACTION_TRE_V defines the set of valid field names. An error is
raised if invalid field names are requested.

Returns 1 if successful, 0 if no record found.

**Implementation**

The "bi" version of this function (ie, biInvoiceTransactionFetch&) is
implemented as a wrapper around the InvoiceTransactionFetch&EPM callback
function.   InvoiceTransactionFetch& is implemented using the
FetchDetailFuncNDRx class.

NVL(ADJUSTMENT_DATE, PAYMENT_DATE) is passed as the order by clause parameter
to the FetchDetailFuncNDRx constructor.

[Contents][Functions]  

* * *

### Function biInvoiceTransactionFetch&(2)

**Declaration**

        
                biInvoiceTransactionFetch&(InvoiceId&,
                                     const FieldNames$[],
                                     var FieldValues?[],
                                     FromRowNr&,
                                     ToRowNr&)

**Parameters**

InvoiceId& | ID of the invoice on which to perform the fetch.  
---|---  
FieldNames$[] | Names of the fields from the INVOICE_TRANSACTION_TRE_V view whose values are to be returned.  If this array is empty then all fields are returned.  
FieldValues?[] | Out: Two dimensional array of fetched rows, FieldValues?[0][] being the first row retrieved.  
The rows are ordered by NVL(ADJUSTMENT_DATE, PAYMENT_DATE).  
FromRowNr& | Number of the first row to return.  The first row is numbered 1.  
ToRowNr& | Number of the last row to return.  The first row is numbered 1.  
A TowRowNr& of <=0 implies that all rows from FromRowNr& onwards are to be
returned.  
  
**Returns**

Zero if no rows are returned, or one greater than the number of rows returned
if there are unfetched rows after ToRowNr& (which implies an additional fetch
is required), or otherwise the number of rows returned.

**Description**

Returns rows of field values from the INVOICE_TRANSACTION_TRE_V view by
performing a query on InvoiceId&.  The names of the fields to retrieve are
passed in FieldNames$[] and their values are returned in the two dimensional
array FieldValues?[].

INVOICE_TRANSACTION_TRE_V defines the set of valid field names.  An error is
raised if an invalid field name is requested.

This function retrieves the value of the MAX_INVOICE_TRANSACTION_DAYS
attribute of the configuration item of type `SYSTEM_CLIENT` with a sequence
number of 1.  If this value is defined and is non-negative then the function
determines the balance of the invoice's account as at
MAX_INVOICE_TRANSACTION_DAYS days ago and the date/time at which this balance
came into effect.  This is then the earliest effective date/time of the subset
of the INVOICE_TRANSACTION_TRE_V rows retrieved for the invoice by this
function.

**Implementation**

This function is implemented as a wrapper around the
zInvoiceTransactionFetch&EPM function which constructs the appropriate SQL
query and then returns the result of the biSQLQuery&(2) function (hence the
nature of the return values described above).

[Contents][Functions]  

* * *

### Function [bi]InvoiceUpdate&

**Declaration**

        
                [bi]InvoiceUpdate&(InvoiceId&,
                           var LastModified~,
                           const FieldNames$[],
                           const FieldValues?[])

**Parameters**

InvoiceId& | ID of the invoice on which to perform the update.  
---|---  
LastModified& | The current last modified date and time of the INVOICE record being updated.  
OUT: The new last modified date and time.  
FieldNames$[] | Names of the fields from the view INVOICE_TRE_V whose values are to be updated.  
FieldValues?[] | Array of new field values.  
  
**Returns**

Returns 1 if successful. Raises an error otherwise.

**Description**

Updates invoice details. _Only the fieldINVOICE_TRE_V.PAYMENT_DUE_DATE may be
updated._

**Implementation**

The "bi" version of this function (ie, biInvoiceUpdate&) is implemented as a
wrapper around the InvoiceUpdate& EPM callback function.  InvoiceUpdate& is
implemented by direct instantiation of the UpdateFunc class.

The InvoiceDb class is derived from the RDB Database class to override the
CreateRules() method.  An instance of the InvoiceTable class is instantiated
in CreateRules() and all fields other than PAYMENT_DUE_DATE are disallowed for
update.

[Contents][Functions]  

* * *

### Function biInvoiceAllocate&

**Declaration**

        
                biInvoiceAllocate&(InvoiceId&,
        		   var LastModified~)

**Parameters**

InvoiceId& | Internal identifier of the invoice to apply and related payments and adjustments to allocate.  
---|---  
LastModified~ | Date/time at which invoice was last modified.  
  
**Returns**

Returns '1' if successful. Raises an error otherwise.

**Description**

This function allocates any payments and adjustments with credit amounts
outstanding to this invoice.  It also supports the allocation of other
invoices to this invoice.  An example of an invoice being allocated to another
invoice would be a Credit Note (which is represented by an invoice as opposed
to an adjustment).

The allocation algorithm can be supplied via the invoice's invoice type
(INVOICE_TYPE_HISTORY.ALLOCATION_FUNCTION_DEFN_ID).  If this field is NULL,
the allocation algorithm defaults to the  biInvoiceAllocateArrears&(2)
function.

There are two types of interface supported for the allocation algorithm:

       * An interface that supports only allocations of payments and adjustments to the specified InvoiceId&. 
       * An interface that in addition to allocations of payments and adjustments, also  supports allocation of other invoices to the specified InvoiceId&. 

See the INVOICE_TYPE_HISTORY.ALLOCATION_FUNCTION_DEFN_ID description for
further details on the supported interfaces.

**Implementation**

The biInvoiceAllocate& function is implemented as an EPM function with the
algorithm as follows.

Determine whether there is a default allocation algorithm specified for this
invoice type.   If there is not, then use  biInvoiceAllocateArrears&(2).

Apply the appropriate allocation algorithm to the invoice.

For each unique payment allocation returned:

> Call biPaymentInvoiceUpdate& to maintain the PAYMENT_INVOICE table for
> accounts that are associated with this payment.

For each unique adjustment allocation returned:

> Call biAdjustmentInvoiceUpdate& to maintain the ADJUSTMENT_INVOICE table for
> accounts that are associated with this adjustment.

For each unique invoice allocation returned, for _both_ the invoice being
allocated as well as the recipient invoice:

>        * Maintain the CURRENT_DUE within the INVOICE table.  
>  
>        * Add a new record into the INVOICE_HISTORY table for the appropriate
> Invoice Id / Receivable Id combination, setting the ALLOCATED_INVOICE_ID.
> [Note: The Receivable Id will be NULL if the allocation isn't associated
> with a Receivable Type.]  Use whichever is the more recent of the
> ISSUE_DATEs of the invoice being allocated and the recipient invoice to
> dictate the insertion point for the new record.  Adjust the
> EFFECTIVE_END_DATE of the record immediately before the new record, and if
> required re-sync any subsequent records including adjusting PREVIOUS_DUE and
> CURRENT_DUE.  If the CURRENT_DUE becomes 0, set the EFFECTIVE_END_DATE of
> the last record to be 1 second less than the EFFECTIVE_START_DATE

> For each allocation returned with an associated Receivable Type:
>
>        * Maintain the CURRENT_DUE within the  INVOICE_RECEIVABLE_TYPE table
> for the appropriate Invoice Id / Receivable Id combination.

[Contents][Functions]  

* * *

### Function biInvoiceDeallocate&

**Declaration**

        
                biInvoiceDeallocate&(InvoiceId&,
                             var LastModified~)

**Parameters**

InvoiceId& | Internal identifier of the invoice to unapply and related payments and adjustments to deallocate.  
---|---  
LastModified~ | Date/time at which invoice was last modified.  
  
**Returns**

Returns '1' if successful. Raises an error otherwise.

**Description**

This function deallocates any payments and adjustments from the invoice.
Payment and adjustment amounts associated with the invoice are updated back to
general credit amounts.  Also deallocates any other Invoices allocated to the
given invoice. This function is typically called prior to calling the
biInvoiceUnapply& function.

**Implementation**

The biInvoiceDeallocate& function is implemented as an EPM function with the
algorithm as follows.

For each unique payment associated with this invoice:

        Call biPaymentInvoiceUpdate& to maintain the PAYMENT_INVOICE table for accounts that are associated with each payment.

For each unique adjustment associated with this invoice:

        Call biAdjustmentInvoiceUpdate& to maintain the ADJUSTMENT_INVOICE table for accounts that are associated with each adjustment.

For each unique other invoice associated with this invoice, for _both_ the
invoice being allocated as well as the recipient invoice:

>        * Maintain the CURRENT_DUE within the INVOICE table.  
>  
>        * Remove the appropriate record from the INVOICE_HISTORY table for
> the Invoice Id / Receivable Id combination. [Note: The Receivable Id will be
> NULL if the allocation isn't associated with a Receivable Type.]  Adjust the
> EFFECTIVE_END_DATE of the record immediately before the new record, and if
> required re-sync any subsequent records including adjusting PREVIOUS_DUE and
> CURRENT_DUE.  Ensure the EFFECTIVE_END_DATE of the last record is set to the
> MAX_DATE.

> For each associated Receivable Type:
>
>        * Maintain the CURRENT_DUE within the  INVOICE_RECEIVABLE_TYPE table
> for the appropriate Invoice Id / Receivable Id combination.  
>  

[Contents][Functions]  

* * *

### Function biInvoicePrint&

**Declaration**

        
                biInvoicePrint&(BillRunId&,
                        EffectiveDate~,
                        BillRunOperationId&,
                        InvoicePrintConfigItemSeqnr&,
                        RootCustomerNodeList&[],
                        var SuccessCustomerNodeList&[],
                        var ErrorCustomerNodeList&[],
                        var OperationStatistics?{})

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the printing of invoices.  It is used to select invoice images having the same bill run Id as this bill run operation and to lock and unlock customers that have invoices ready for printing.  
InvoicePrintConfigItemSeqnr& | IN: Sequence number for the 'INVOICE_PRINT' configuration item to use when printing the invoices.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoices output for printing.  All invoicing child customer nodes will also have their invoices sent to the appropriate output device for printing.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoices sent to the appropriate output device for printing.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoices sent to the appropriate output device for printing.  
OperationStatistics?{} | OUT: Unknown EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains:
      1. Key: Images  
The number of images printed associated with the run.  
  
  
**Returns**

Returns '1' if successful. Raises an error otherwise.

**Description**

The function biInvoicePrint& is used to retrieve invoice images from previous
billing operations and send them to the appropriate output device for
printing.

All root customer nodes in the _RootCustomerNodeList &[]_ are first checked if
they are available for processing (unlocked) in the CUSTOMER_NODE table.   If
so, the lock is obtained for that root customer by updating their
corresponding row with the specified bill run operation Id and derived bill
run and process Ids.   Any root customers that were unable to obtain a lock
for are added into the _ErrorCustomerNodeList &[]._

The details for INVOICE_PRINT configuration item type with sequence number =
_InvoicePrintConfigItemSeqnr &_ will be used to configure GOP (General Output
Process) parameters.  The attributes for INVOICE_PRINT are:

       * OUTPUT_METHOD - output method for storing printing details 
       * TMP_DIR - directory for holding temporary files used by the GOP
       * ERROR_THRESHOLD - maximum amount of non-fatal errors before the GOP terminates
       * MAX_CHILD_PROCESSES - maximum number of child processes for the GOP to use for parallel output of images.
       * GOP_COMMAND_OPTIONS - additional command line options that will be passed to the GOP process.

A call to the GOP is made in billing output mode (mode 1) of operation to
process the invoices to output.  On completion (successfully or not) of the
GOP, the CUSTOMER_NODE_BILL_RUN table will be queried to determine whether the
root customer nodes where successful or not and add them to the appropriate
_SuccessCustomerNodeList &[] _or _ErrorCustomerNodeList &[] _arrays _._

_OperationStatistics?{}_ returned by the function is:

       * 'Images' - Number of rows in the INVOICE_CONTENTS table that have images printed associated with the bill run.

Any locks that were obtained for root customer nodes in the CUSTOMER_NODE
table will now be released.

**Implementation**

The biInvoicePrint& is implemented as an EPM function that makes a single call
to biCommandRunGetResults& to execute the GOP.  If MAX_CHILD_PROCESSES is
greater than 1 then it adds the '-c <MAX_CHILD_PROCESSES>'   option to the
generated gop command to cause it to run in  multi-process mode. If
GOP_COMMAND_OPTIONS is specified then it will be added as command line
arguments to the GOP.

[Contents][Functions]  

* * *

### Function biInvoiceAllocateCustomers&

**Declaration**

        
                biInvoiceAllocateCustomers&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EffectiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the allocation of invoices to payments and adjustments for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoices allocated.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoices allocated.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoices allocated.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains:
      1. Key: InvoicesAllocated  
The number of invoices allocated.  
  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Invoice Allocation" billing operation
for a set of customers.  For each customer, it finds all applied invoices for
the customer on the bill run, and then for each invoice found it calls
biInvoiceAllocate&() to allocate the invoice to any payments or adjustments
with unallocated amounts for the invoice's account.

If a non-null value is returned by BillRunZeroAdjustmentType?{}(), an auto-
allocated zero value adjustment is inserted against all AR accounts in the
customer hierarchy that have both credit and debit amounts. With the default
allocation algorithms this has the effect of offsetting debits against credits
within and across transactions such that only debits or only credits remain
and there is no net change to the current due.

A lock is obtained on each customer as it is processed, and the success or
otherwise of the allocation is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  For each customer the
function zbiInvoiceAllocateForCustomer() is called. This function performs the
query to identify all applied invoices for this bill run and customer.  It
calls biInvoiceAllocate&() for each invoice found.

For accounts where a zero value adjustment is applicable,
(f)EV_AdjustmentInsert& is called to insert a zero value adjustment with auto-
allocation enabled.

[Contents][Functions]  

* * *

### Function biInvoiceDeallocateCustomers&

**Declaration**

        
                biInvoiceDeallocateCustomers&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the de-allocation of invoices from payments and adjustments for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoices de-allocated.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoices de-allocated.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoices de-allocated.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains:
      1. Key: InvoicesDeallocated  
The number of invoices de-allocated.  
  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Revoke Invoice Allocation" billing
operation for a set of customers.  For each customer, it finds all invoices on
the bill run which have been allocated to one or more payments and
adjustments, and de-allocates them by calling biInvoiceDeallocate&().

A lock is obtained on each customer as it is processed, and the success or
otherwise of the allocation is recorded in the CUSTOMER_NODE_BILL_RUN table.



**Implementation**

This function is implemented as a remote EPM function.  For each customer the
function zbiInvoiceDeallocateForCustomer() is called. This function performs
the query to identify all allocated invoices for this bill run and customer.
It calls biInvoiceDeallocate&() for each invoice found.

[Contents][Functions]

* * *

### Function biInvoiceRevoke&

**Declaration**

        
                biInvoiceRevoke&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var SuppressedCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  invoices for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoices revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoices revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoices revoked.  
SuppressedCustomerNodeList&[] | OUT: A list of root customer nodes whose invoices have been suppressed as a result of calling this function as part of an "Invoice/Statement Generation" billing operation.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
InvoicesDeleted | The number of invoices deleted during the revoke  
StatementsDeleted | The number of statements deleted during the revoke  
InvoiceAmount | The sum of the invoice amounts revoked.  
StatementAmount | The sum of the statement amounts revoked.  
ChargesDeleted | The number of charge records deleted as part of the revoke.  
(Charge records generated by the biller for the revoked invoices.)  
ChargesUpdated | The number of charge records updated as part of the revoke.  
(Charge records generated by the rater that were associated with the revoked
invoices.)  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Revoke Invoices/Statements" billing
operation for a set of customers.  For each customer, it finds all invoices or
statements on the bill run.  For each invoice or statement it:

      1. Deletes all charges associated with the invoice or statement that were generated by the biller.
      2. Updates all charges associated with the invoice or statement that were generated by the rater.
      3. Deletes the invoice or statement record together with its receivable type breakdown (if any).

Due to the large number of charges that may be associated with  an invoice or
statement, period commits are performed during the first and second
operations.

This function also has special support for being called as part of an
"Invoice/Statement Generation" operation to revoke invoices and statements
that were generated by the biller but have been marked as suppressed.  In this
mode the successfully processed customers are returned in
SuppressedCustomerNodeList&[].

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  For each customer the
function zbiInvoiceRevokeForCustomer&() is called. This function checks that
none of the invoices for the customer have been applied or have had images
generated before performing the revoke.  It also checks that none of the
invoices are associated with any consolidated statements (i.e. none where
CONSOLIDATED_INVOICE_IND_CODE is 1) or vice versa that no statements reference
a consolidated invoice (i.e. none where CONSOLIDATION_INVOICE_ID is set).
Checks are also made for the presence of any inter-hierarchy charges
associated with other invoices.  If these are present then it is necessary to
revoke the other invoices first.

The function determines that it is being called to revoke suppressed invoices
or statements by detecting a primary key violation when it attempts to insert
the CUSTOMER_NODE_BILL_RUN record.

[Contents][Functions]

* * *

### Function biInvoiceRevokeParallel&

**Declaration**

        
                biInvoiceRevokeParallel&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            RevokeParallelConfigItemSeqnr&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EffectiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  invoices for these customers.  
RevokeParallelConfigItemSeqnr& | IN: Sequence number for the 'INVOICE_REVOKE_PARALLEL' configuration item to use when revoking the invoices.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoices revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoices revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoices revoked.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
InvoicesDeleted | The number of invoices deleted during the revoke  
StatementsDeleted | The number of statements deleted during the revoke  
InvoiceAmount | The sum of the invoice amounts revoked.  
StatementAmount | The sum of the statement amounts revoked.  
ChargesDeleted | The number of charge records deleted as part of the revoke.  
(Charge records generated by the biller for the revoked invoices.)  
ChargesUpdated | The number of charge records updated as part of the revoke.  
(Charge records generated by the rater that were associated with the revoked
invoices.)  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Revoke Invoices/Statements" billing
operation for a set of customers when multi-processing capability is required.

**Implementation**

This function is implemented as a remote EPM function. This function is
responsible for root customer node locking and unlocking and performs the
initial insertion into the CUSTOMER_NODE_BILL_RUN table updating a node's
status to running.

The perl script revoke_invoice_parallel.pl is used to perform the actual
processing, as it implements multiprocess calls to
zbiInvoiceRevokeForCustomer&().

The details for INVOICE_REVOKE_PARALLEL configuration item type with sequence
number = _InvoiceRevokeParallelItemSeqnr &_ will be used to configure the
following parameters.  The attributes for INVOICE_REVOKE_PARALLEL are:

       * MAX_CHILD_PROCESSES - maximum number of child processes to spawn.

Statistics for this function are captured by parsing the output of the perl
script.

[Contents][Functions]

* * *

### Function biInvoiceImageRevoke&

**Declaration**

        
                biInvoiceImageRevoke&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  invoice images for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoice images revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoice images revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoice images revoked.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
Images | The number of images deleted.  
Invoices | The number of invoices or statement whose images have been deleted.  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Revoke Invoice/Statement Images" billing
operation for a set of customers.  For each customer, it finds all invoices or
statements on the bill run.  For each invoice or statement it:

      1. Checks that they have not already been applied.
      2. Deletes any images associated with the invoice or statement.
      3. Updates the invoice or statement record to indicate that it no longer has any images generated.

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  For each customer the
function zbiInvoiceImageRevokeForCustomer&() is called.   All images for a
customer are deleted as part of a single transaction.

[Contents][Functions]

* * *

### Function biInvoiceImageMinimalRevoke&

**Declaration**

        
                biInvoiceImageMinimalRevoke&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  invoice images for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their invoice images revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their invoice images revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their invoice images revoked.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
Images | The number of images deleted. This will always be zero as this function performs a minimal revoke, where no deletes are performed.   
Invoices | The number of invoices or statement whose images have been deleted. This will always be zero as this function performs a minimal revoke, where no deletes are performed.   
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Revoke Invoice/Statement Images" billing
operation for a set of customers, where minimal revoke functionality is
required.  For each customer, it finds all invoices or statements on the bill
run.  For each invoice or statement it checks that they have not already been
applied. Unlike the full operation it _does not delete_ any images associated
with the invoice or statement.

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  Functionality is
shared with  biInvoicePrintMinimalRevoke&() via the function
zbiInvoiceCommonMinimalRevoke&().

[Contents][Functions]

* * *

### Function biInvoicePrintRevoke&

**Declaration**

        
                biInvoicePrintRevoke&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  printed invoice images for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their printed invoice images revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their printed invoice images revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their printed invoice images revoked.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
Images | The number of images for which printing was revoked.  
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Discard Printing of Invoices" billing
operation for a set of customers.  For each customer, it finds all invoices or
statements images on the bill run.  For each invoice or statement image it
clears the flag indicating that the image has been printed.

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  For each customer the
function zbiInvoicePrintRevokeForCustomer&() is called.   All print settings
for a customer are reset as part of a single transaction.

[Contents][Functions]

* * *

### Function biInvoicePrintMinimalRevoke&

**Declaration**

        
                biInvoicePrintMinimalRevoke&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            const RootCustomerNodeList&[],
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EfefctiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: Internal identifier of the bill run operation that is being processed for the revoking of  printed invoice images for these customers.  
RootCustomerNodeList&[] | IN: List of root customer node Ids that are to have their printed invoice images revoked.  
SuccessCustomerNodeList&[] | OUT: A list of root customer node Ids that successfully had their printed invoice images revoked.  
ErrorCustomerNodeList&[] | OUT: A list of root customer node Ids that failed to have all of their printed invoice images revoked.  
Statistics?{} | OUT: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
Images | The number of images for which printing was revoked. This will always be zero as this function performs a minimal revoke.   
  
**Returns**

Returns the number of customers successfully processed if successful. An error
is raised otherwise.

**Description**

This function is used to perform the "Discard Printing of Invoices" billing
operation for a set of customers, where minimal revoke functionality is
required.  Unlike the full operation it _does not clear_ the flag indicating
whether an image has been printed.  This function would be used in conjunction
with  biInvoiceImageMinimalRevoke& where a minimal revoke means invoice and
statement images are not deleted.

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

**Implementation**

This function is implemented as a remote EPM function.  Functionality is
shared with biInvoiceImageMinimalRevoke&() via the function
zbiInvoiceCommonMinimalRevoke&().

[Contents][Functions]

* * *

### Function biInvoiceConsolidate&

**Declaration**

        
                biInvoiceConsolidate&(
                        BillRunId&,
                        EffectiveDate~,
                        BillRunOperationId&,
                        QAInd&,
                        const RootCustomerNodeList&[],
                        var SuccessCustomerNodeList&[],
                        var ErrorCustomerNodeList&[],
                        var OperationStatistics?{})

**Parameters**

BillRunId& | In:  Internal identifier for the bill run for which to consolidate statements.  
---|---  
EffectiveDate~ | In:  The effective date of the bill run.  
BillRunOperationId& | In:  The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
QAInd& | In:  Indicates whether a "real" bill run is to be processed or if a QA bill run is to be processed. TRUE indicates a QA Run.  
RootCustomerNodeList&[] | In:  The list of root customer nodes whose statements are to be consolidated.  The list may not be empty.  
SuccessCustomerNodeList&[] | Out:  A list of all root customer ids that were successfully processed.  This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | Out:  A list of root customer nodes for which there were statements eligible for consolidation, but where consolidation failed.  
OperationStatistics?{} | Out: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
ConsolidatedInvoicesGenerated | The number of consolidated invoices generated as part of this operation.  
StatementsConsolidated | The number of statements consolidated into invoices as part of this operation.  
TotalCustomerNodes | The number of customer nodes that are processed as part of this operation.  
ConsolidatedInvoiceAmount | The total amount consolidated from statements into invoices in the currency of the bill run type.  
  
**Returns**

1 if successful. An error is raised otherwise.

**Description**

This function takes an ordered list of root customer node ids, and for each
root customer determines if any account within the hierarchy requires a
consolidated invoice to be generated. The consolidation expression is
evaluated to determine if statements pending consolidation for that account
are eligible for consolidation. For each consolidated invoice that is
generated, the function inserts an invoice record into the database and
updates all statements being consolidated to reflect that they have been
consolidated.

**Implementation**

This function is implemented as a remote EPM function which executes in the
biBillRunRO service.

For the specified bill run, it processes each root hierarchy within
RootCustomerNodeList&[]. For each root customer node it queries the view
INV_PENDING_CONSOLIDATION_V to retrieve all accounts in the current hierarchy
with statements pending consolidation. For each returned row :-

      1. Assign the direct variables associated with the view  INV_PENDING_CONSOLIDATION_V to the values returned from the query.
      2. Determine eligibility for consolidation by evaluating the appropriate INVOICE_CONSOLIDATION_EXPR as defined within the  INVOICE_TYPE_HISTORY table.
      3. If the invoice consolidation expression returns TRUE (1), or if no invoice consolidation expression is defined, then retrieve all eligible statements pending consolidation for the appropriate account. This includes all records in the INVOICE table with PENDING_CONSOLIDATION_IND_CODE set to 1, QA_IND_CODE matches the specified `QAInd&` and an ACCOUNT_ID matching either the account being processed or an account with a TRANSFERRED_ACCOUNT_ID matching the account being processed.
      4. Populate direct variables associated with  INV_INVOICE_V and evaluate the invoice type expressions.
      5. Insert a consolidated invoice record into the  INVOICE table for the appropriate account. The following table lists the fields that are populated. All other fields will be undefined unless explicitly populated via the invoice type expressions. Column| Value  
---|---  
LAST_MODIFIED| Current date and time  
CUSTOMER_INVOICE_STR| INVOICE_ID  
INVOICE_TYPE_ID| As per the row in ` INV_PENDING_CONSOLIDATION_V`  
BILL_RUN_ID| `BillRunId&`  
QA_IND_CODE| `QAIndCode&`  
ACCOUNT_ID| As per the row in ` INV_PENDING_CONSOLIDATION_V`  
CUSTOMER_NODE_ID| As per the row in ` INV_PENDING_CONSOLIDATION_V`  
EFFECTIVE_DATE| `EffectiveDate~`  
ISSUE_DATE| `EffectiveDate~`  
ORIGINAL_PAYMENT_DUE_DATE| `EffectiveDate~`  
PAYMENT_DUE_DATE| As retrieved for the most recent statement being
consolidated that is associated with the account being processed (that is, the
most recent non-transferred statement pending consolidation)  
INVOICE_AMOUNT| STATEMENT_AMOUNT + TRANSFERRED_STATEMENT_AMOUNT as per the row
in ` INV_PENDING_CONSOLIDATION_V`  
BALANCE_FORWARD| As retrieved for the oldest statement being consolidated that
is associated with the account being processed (that is, the most recent non-
transferred statement pending consolidation)  
ACCOUNT_BALANCE| BALANCE_FORWARD + INVOICE_AMOUNT  
ACCOUNT_INITIAL_DUE| ACCOUNT_BALANCE  
CURRENT_DUE| INVOICE_AMOUNT  
TOTAL_PAYMENTS| Sum TOTAL_PAYMENTS of all statements being consolidated  
TOTAL_ADJUSTMENTS| Sum TOTAL_ADJUSTMENTS of all statements being consolidated  
UNBILLED_AMOUNT| Sum UNBILLED_AMOUNT of all statements being consolidated  
CONSOLIDATED_INVOICE_IND_CODE| 11  
      6. Insert the appropriate consolidated Invoice records into the  INVOICE_HISTORY and  INVOICE_RECEIVABLE_TYPE tables.
      7. For each statement that was consolidated, within the  INVOICE table set PENDING_CONSOLIDATION_IND_CODE to NULL and CONSOLIDATION_INVOICE_ID to the consolidated Invoice Id.  Also if GL functionality is enabled, then reset UNPOSTED_IND_CODE to 1 within the  INVOICE_GL_GUIDANCE table for all records associated with this consolidated statement. 

A lock is obtained on each customer as it is processed, and the success or
otherwise of the operation is recorded in the CUSTOMER_NODE_BILL_RUN table.

> _

_

[Contents][Functions]

* * *

### Function biInvoiceConsolidateRevoke&

**Declaration**

        
                biInvoiceConsolidateRevoke&(
                          BillRunId&,
                          EffectiveDate~,
                          BillRunOperationId&,
                          const RootCustomerNodeList&[],
                          var SuccessCustomerNodeList&[],
                          var ErrorCustomerNodeList&[],
                          var OperationStatistics?{})

**Parameters**

BillRunId& | In:  Internal identifier for the bill run for which to un-consolidate statements.  
---|---  
EffectiveDate~ | In:  The effective date of the bill run.  
BillRunOperationId& | In:  The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
RootCustomerNodeList&[] | In:  The list of root customer nodes whose consolidated invoices are to be revoked.  The list may not be empty.  
SuccessCustomerNodeList&[] | Out:  A list of all root customer ids that were successfully processed.  This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | Out:  A list of root customer nodes for which there existed consolidated invoices for the given bill run, but where the revoke failed.  
OperationStatistics?{} | Out: EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers.  The operation statistics structure contains: | **Key** | **Description**  
---|---  
ConsolidatedInvoicesDeleted | The number of consolidated invoices deleted as part of this revoke operation.  
StatementsUnconsolidated | The number of statements unconsolidated as part of this revoke operation.  
ConsolidatedInvoiceAmount | The total amount unconsolidated from deleted invoices in the currency of the bill run type.  
  
**Returns**

1 if successful. An error is raised otherwise.

**Description**

biInvoiceConsolidateRevoke& takes an ordered list of root customer node id's,
and for each root customer, retrieves all the consolidated invoices for the
specified bill run associated with all customer nodes, in the specified root
customer's hierarchy, and un-consolidates each invoice.

If a consolidated Invoice is found which is either applied or has had images
generated, then a record is inserted into the  CUSTOMER_NODE_BILL_RUN table
with a status of failure and a message indicating why consolidation can not be
revoked in this customer hierarchy. The root customer node id is then placed
in ErrorCustomerNodeList&[] and the next root customer node id in
RootCustomerNodeList&[] is processed.

If a customer hierarchy does not have any consolidated invoices associated
with this bill run, then a record is inserted into the  CUSTOMER_NODE_BILL_RUN
table with a status of success. The root customer node id is then placed in
SuccessCustomerNodeList&[] and the next root customer node id in
RootCustomerNodeList&[] is processed.

**Implementation**

This function is implemented as a remote EPM function which executes in the
biBillRunRO service.

For the specified bill run, it performs the following for each customer node
in each root hierarchy within RootCustomerNodeList&[]:

Retrieve all consolidated Invoices (identified by
CONSOLIDATED_INVOICE_IND_CODE set to 1 in the  INVOICE table).  If a
consolidated Invoice is found which is either applied or has had images
generated, then the entire customer hierarchy is skipped, a record is inserted
into the  CUSTOMER_NODE_BILL_RUN table with a status of failure and a relevant
error message.

For each valid consolidated Invoice found:

      1. Retrieve associated consolidated Statements (identified by CONSOLIDATION_INVOICE_ID in the  INVOICE table matching the Id of the consolidated Invoice)
      2. For each consolidated Statement found, set the  CONSOLIDATION_INVOICE_ID to NULL and PENDING_CONSOLIDATION_IND_CODE to 1.
      3. Delete the record for the consolidated Invoice from the  INVOICE table.  Delete the appropriate records from the INVOICE_HISTORY and  INVOICE_RECEIVABLE_TYPE tables. 

A lock is obtained on each customer as it is processed, and the success or
otherwise of the revoke is recorded in the CUSTOMER_NODE_BILL_RUN table.

[Contents][Functions]  

* * *

### Function biInvoicePrepaidGenerate&

**Declaration**

        
                biInvoicePrepaidGenerate&(
            BillRunId&,
            EffectiveDate~,
            BillRunOperationId&,
            RootCustomerNodeList&[],
            UsageChargesBeforeBillDate&,
            var SuccessCustomerNodeList&[],
            var ErrorCustomerNodeList&[],
            var SuppressedCustomerNodeList&[],
            var Statistics?{})
        

**Parameters**

BillRunId& | IN:  Internal identifier of the bill run being processed  
---|---  
EffectiveDate~ | IN: The effective date of the bill run.  
BillRunOperationId& | IN: The unique id of this particular operation. Used to populate the CUSTOMER_NODE_BILL_RUN table.  
RootCustomerNodeList&[] | IN: The list of pre-paid root customer nodes which need invoices generating. The list will contain a single entry in the case of an on-demand bill run. All services associated with customers in the hierarchy must be pre-paid. The list may not be empty.  
UsageChargesBeforeBillDate& | IN: The effect of this parameter is the same as the configuration attribute USAGE_CHARGES_BEFORE_BILL_DATE in the BGP configuration item.  
SuccessCustomerNodeList&[] | OUT: A list of all root customer IDs that were successfully processed. This list is a subset of the RootCustomerNodeList&[] parameter and must preserve the RootCustomerNodeList&[] order.  
ErrorCustomerNodeList&[] | OUT: A list of root customer IDs that were not successfully processed by the pre-paid bill run.  
SuppressedCustomerNodeList&[] | OUT: A list of all of the root customer IDs whose invoices were suppressed.  
Statistics?{} | OUT: Unknown EPM hash returned to the calling program containing the statistics gathered during the processing of the list of root customers. The statistics structure contains:
      1. Key: TotalCharges  
The number of original charges that are processed by the bill run.

      2. Key: TotalCustomerNodes  
The number of customer nodes that are processed by the bill run.

      3. Key: Invoices  
Total number of invoices generated for this bill run.

      4. Key: Statements  
Total number of statements generated for this bill run.

      5. Key: InvoiceAmount  
Sum total of the invoiced amount generated by the bill run.

      6. Key: StatementAmount  
Sum total of the statement amount generated by the bill run.  
  
**Returns**

1 if successful. An error is raised otherwise.

**Description**

biInvoicePrepaidGenerate& is an alternative to the BGP's biInvoiceGenerate&
which allows statements to be generated for prepaid hierarchies, with greater
performance than can be achieved using standard BGP functionality. The context
processing of the BGP is needlessly slow for prepaid with statements
hierarchies that do not have configuration dependent on the capabilities of
the BGP.

This function takes an ordered list of root customer node ids from the billing
controller and then generates statements (invoice records) for each hierarchy
in turn at the effective date specified. The process is single stream per bill
run operation (and hence per customer hierarchy). As such, it may not be ideal
for use in processing large prepaid with statements corporate hierarchies or
high volume services. Since context processing is not performed (as in the
BGP) the hierarchies passed must contain only prepaid subscribers (that is,
there can be no convergent pre/post-paid subscribers) and configuration cannot
rely on BGP functionality such as billing tariffs, subtotals and invoice
expressions as these will not be evaluated.

biInvoicePrepaidGenerate& is responsible for applying and releasing locks on
customers. It is also responsible for supplying the calling program with lists
of successful, erred and suppressed root customer nodes.

The GLGuidance?[]() function is not invoked for any charges - hence all rating
charges associated with the specified set of customers must only have earned
but un-billed (EBUB) GL Guidance entities associated with them. The generation
of invoices/statements via this function will not result in any changes to the
sales journal.

This function cannot be called as part of a Quality Assurance bill run.

Unlike BGP processing, the charges updated by this function will not have
their INVOICE_SECTION_NR and INVOICE_ITEM_NUMBER columns updated.

**Implementation**

biInvoicePrepaidGenerate& is implemented as a remote EPM function which
executes in the biBillRunRO service. It performs the following operations for
each customer node in a hierarchy recursively (from the bottom up):

      1. Retrieve all of the charges for the customer node
      2. Total up invoice, statement and unbilled amounts for each account
      3. Total up any payments or adjustments for each account
      4. Mark the all of the charges as billed
      5. Insert the invoice for each account into the database
      6. Insert appropriate INVOICE_HISTORY record for invoice
      7. Pass up any statement amounts for non-reporting nodes to the next highest customer node

The pre-paid bill run step will populate the following INVOICE record fields.
The fields will be populated as per the SAS entry for the INVOICE table unless
otherwise stated below. Any fields not listed below will be set to NULL.

INVOICE_ID |    
---|---  
LAST_MODIFIED |    
CUSTOMER_INVOICE_STR | Will be set to the string representation of INVOICE_ID. This can not be customised as Invoice Expressions will not be evaluated.  
INVOICE_TYPE_ID |    
BILL_RUN_ID | Set to the value of input parameter BillRunId&.  
RUNNING_IND_CODE |    
QA_IND_CODE | This will always be NULL for a pre-paid bill run as QA mode is not supported for pre-paid billing.  
SUPPRESS_IND_CODE | Will always be NULL for a pre-paid bill run. Any suppressed invoices are never inserted.  
ACCOUNT_ID |    
INVOICED_ACCOUNT_ID |    
CUSTOMER_NODE_ID |    
EFFECTIVE_DATE | Set to the value of input parameter EffectiveDate~.  
ISSUE_DATE | Will be equal to EFFECTIVE_DATE because Invoice Expressions are not evaluated.  
ORIGINAL_PAYMENT_DUE_DATE | Will be equal to EFFECTIVE_DATE because Invoice Expressions are not evaluated.  
PAYMENT_DUE_DATE | Will be equal to EFFECTIVE_DATE because Invoice Expressions are not evaluated.  
INVOICE_AMOUNT |    
STATEMENT_AMOUNT |    
BALANCE_FORWARD |    
ACCOUNT_BALANCE | If the invoice is associated with a liability account and the v8.00 accounting functionality is enabled :-  
  
BALANCE_FORWARD - DeltaAmount  
  
otherwise :-  
  
BALANCE_FORWARD + DeltaAmount  
  
where "DeltaAmount" is equal to INVOICE_AMOUNT for invoicing accounts and
STATEMENT_AMOUNT for statement accounts  
ACCOUNT_INITIAL_DUE |    
CURRENT_DUE | Will be set to INVOICE_AMOUNT.  
TOTAL_PAYMENTS | Will be equal to the total amount of payments made to the pre-paid account in the billing period. See INVOICE for calculations.  
TOTAL_ADJUSTMENTS | Will be equal to the total amount of adjustments made to the pre-paid account in the billing period. See INVOICE for calculations.  
UNBILLED_AMOUNT | This will equal the sum of all charges to the account whose tariff has ACCOUNT_AGGREGATE_IND_CODE set to 1. See INVOICE.  
  
The pre-paid bill run step will also populate the following INVOICE_HISTORY
record fields if invoice amount is not zero. The fields will be populated as
per the SAS entry for the INVOICE_HISTORY table unless otherwise stated below.
Any fields not listed below will be set to NULL.

INVOICE_ID |    
---|---  
LAST_MODIFIED |    
SEQNR | Will be set to 1.  
EFFECTIVE_START_DATE | Will be equal to ISSUE_DATE of INVOICE.  
EFFECTIVE_END_DATE | Will be set to MAX_DATE  
PREVIOUS_DUE | Will be set to 0.0  
CURRENT_DUE | Will be equal to INVOICE_AMOUNT of INVOICE.  
  
**Performance**

To maximise performance, each charge record is retrieved by customer partition
and account id once only using the SQLOpenArray@() interface. Retrieved
charges need to be joined with the tariff_history table to determine which
charges are billable and which charges contribute to each invoice/statement's
UNBILLED_AMOUNT.

Charge records are updated in bulk by row ID using the array interface of
SQLExecute&().

Transactions are committed either:

       * once per customer hierarchy,
       * on completion of processing an account if the total number of uncommitted charge updates is greater than 100, or
       * once for every 500 charges updated within an account
whichever occurs first.

**Invoice Suppression**

Standard invoice suppression is not supported (since no Invoice Expressions
will be evaluated), however any accounts that do not have charges against them
will have their invoice/statement suppressed. If all prime accounts in a
hierarchy are suppressed, then the root customer node id will be added to the
var array parameter SuppressedCustomerNodeList&[].

**Earliest Charge Partition Caching**

biInvoicePrepaidGenerate& will cache the earliest charge partition for each
customer partition locally in the parser's ProcessState?{} variable. This
value will be refreshed if the entry is over 1 hour old.

**Customer Locking**

Before biInvoicePrepaidGenerate& processes a root customer it must obtain a
lock on the customer to prevent any other billing operation from interfering
with it's processing. Locks are obtained by updating the CUSTOMER_NODE table
with the bill run operation id and process id. If these fields are NULL a lock
is obtained. After the customer has been processed, the lock is released to
other billing processes.

biInvoicePrepaidGenerate& obtains, and commits to the database, locks on all
customers before the first customer is processed. These locks are released
after the last customer has been processed. If a lock is not obtained for a
customer then that customer is immediately placed into the erred customer list
and is not processed.

[Contents][Functions]

* * *

### Function InvoiceHistoryFix&

**Declaration**

        
                InvoiceHistoryFix&(InvoiceId&)
        

**Parameters**

InvoiceId& | IN:  Internal identifier of the invoice for which invoice history is to be inserted.  
---|---  
  
**Returns**

1 if invoice history was added and 0 otherwise.

**Description**

This function fixes invoice history for the specified invoice.  It inserts
INVOICE_HISTORY records for the invoice and any payments and adjustments that
have been allocated to the invoice.

If an INVOICE_HISTORY record already exists for the invoice then this function
does nothing.

The database changes are not committed by this function it is assumed that the
caller is in a transaction and will commit when required.

**Implementation**

This function is implemented in epm.

[Contents][Functions]

--------------------------------------------------
## Contents

    Related Documents
    Overview
    Processing
    Rating a Normalised Event
    Rating in a Multi-Tenanted Environment
    Signals
    Tuxedo Event Handling
    Termination
    Commands
    Configuration Parameters
    Command-line Arguments
    Built-in Functions

* * *

## Related Documents

    UTP for the ERT

[Contents]  

* * *

## Overview

This document describes the basic operation of the event rating process (ERT).
The ERT is responsible for receiving normalised events from the Event Rating
Broker (ERB) module and generating charge records which are sent back to the
ERB module.  When an event is received, the ERT process uses the Event Rating
Module (ERM) to evaluate eligible rating tariffs and generate zero or more
charge records for that event.

[Contents]  

* * *

## Processing

On startup, the ERT process:

      1. processes its command-line arguments in order to determine its process number;  
  

      2. initialises its signal handler;  


      3. connects to the database.  


      4. connects to the TRE;  


      5. subscribes to appropriate Tuxedo events and initialises a Tuxedo event handler to capture event details;  


      6. reads its configuration parameters from the database;  


      7. retrieves from the database all currencies and conversion rates defined as at the current date/time and stores these in the global Currency Cache Module (CCM);  


      8. registers several built-in functions with its internal expression parser;  


      9. initialises its Event Rating Module (ERM) as at the current date/time. This module is responsible for retrieving all rating tariffs and associated information from the database and evaluating these tariffs as applicable for each normalised event in order to generate zero or more charges;  


      10. attaches to the ERB module, the Service Cache Module (SCM), the Account Cache Module (ACM), the Customer Node Module (CNM), the Rating Subtotal Cache (RSC) module and the Temporal Entitlement Cache (TEC) module;  


      11. calls rsc_set_rating_mode() with a parameter of `RSC_RATE_AND_STORE` in order to notify the RSC that the results of rating a normalised event should be committed to permanent storage;  


      12. calls  tec_set_rating_mode() with a parameter of `TEC_RATE_AND_STORE` in order to notify the TEC that the results of rating a normalised event should be committed to permanent storage;  


      13. sets the maximum size of the global derived attribute table cache, if required;  


      14. processes any pending unsolicited Tuxedo message captured by the Tuxedo event handler; and  


      15. waits on erb_receive_event() to receive each normalised event to be processed.

If the erb_receive_event() function indicates that a command is pending, the
ERT process retrieves the command by calling erb_receive_command(), then
decodes and processes the command accordingly, then processes any pending
Tuxedo event, then resumes waiting on erb_receive_event().

For each encoded normalised event received from erb_receive_event(), the ERT
process decodes normalised event attributes from the event and assigns them to
the direct variables associated with the NORMALISED_EVENT_V database view.

The event is then rated. If the event was rated successfully, the ERT process
sends each generated charge to the ERB module by calling erb_send_charge().

The ERT process then handles any pending Tuxedo event then resumes waiting on
erb_receive_event().

[Contents]  

* * *

## Rating a Normalised Event

The ERT process performs the following steps in order to rate a normalised
event:

      1. Calls rsc_event_start() to prepare the RSC for updates to rating subtotal values as a result of rating the normalised event.  


      2. Calls  tec_event_start() to prepare the TEC for updates to temporal entitlement allocations as a result of rating the normalised event.  


      3. Calls the ERM::EventRate() method in order to generate charges, update rating subtotals and temporal entitlement allocations, and, if account aggregation is enabled, aggregate unbilled amounts to accounts. A flag that indicates whether the updating of reservation amounts is enabled is also returned from the ERM::EventRate() method so that the ERT can instruct the ACM, RSC and TEC to update or delete reservations on completion of rating an event. If an error occurs the ERT process retrieves the ID and the text of the error, flags the normalised event as an error event by calling erb_error_event(), reverses any rating subtotal updates by calling rsc_event_rollback(), reverses any updates to temporal entitlement allocations by calling tec_event_rollback() and aborts rating of the event.  


      4. If the normalised event is flagged to be discarded after rating then the ERT process reverses any account updates by calling acm_account_rollback_event() (if account aggregation is enabled), reverses any rating subtotal updates by calling rsc_event_rollback(), reverses any updates to temporal entitlement allocations by calling tec_event_rollback(), and then terminates processing of the event.  


      5. If the normalised event is not flagged to be discarded after rating then the ERT process attempts to commit any rating subtotal updates and temporal entitlement updates by calling rsc_event_commit() and  tec_event_commit() (respectively).  If rsc_event_commit() or tec_event_commit() fails then the ERT process reverses any account updates by calling acm_account_rollback_event() (if account aggregation is enabled), reverses any rating subtotal updates by calling rsc_event_rollback(), reverses any updates to temporal entitlement allocations by calling tec_event_rollback(), and then retries up to RATE_RETRY_LIMIT times to execute the above steps. The same retry behaviour applies when evaluating charge(s) for a balance-managed account that would cause the available credit to be exceeded (which may have arisen due to concurrent rating of events). If the retry limit is reached the ERT process retrieves the ID and the text of the RSC, TEC or ACM error (as appropriate) and flags the normalised event as an error event by calling erb_error_event(). 

[Contents]  

* * *

## Rating in a Multi-Tenanted Environment

Rating in a multi-tenanted environment will automatically set the TRE tenant
under certain conditions. Refer to  Rating in  a Multi-Tenanted Environment in
the trerate SAS.

[Contents]  

* * *

## Signals

On receipt of a SIGTERM signal the ERT process terminates.

On receipt of a SIGUSR1 signal the ERT process appends a report on its current
dynamically-allocated memory to the `$ATA_DATA_SERVER_LOG/ert.mem` text file.

The SIGUSR2 signal is used by the event thread to notify the main thread of
the process of an unsolicited message.

The ERT process ignores SIGHUP, SIGINT, SIGQUIT, SIGCLD and SIGPIPE signals.

[Contents]

* * *

## Tuxedo Event Handling

When the ERT process connects to the TRE it uses the treConnectFlags() API
call to specify that it wishes to be notified of unsolicited messages via
thread notification.  It then subscribes to two events: "ERT" and
"ERT:<ProcessNr>" and sets up an unsolicited message handler. Hence using
treEventPostx&(), it is possible to send unsolicited messages to all ERT
processes (using the "ERT" event name), or to direct a message to an
individual ERT (using the "ERT:<ProcessNr>" event name).

When the ERT process receives an unsolicited message the event thread adds the
event details to a list of pending events. Tuxedo has significant restrictions
on what Tuxedo calls can be made in the unsolicited message handler, so it is
not possible to immediately process the event.  The main thread is then
interrupted by the event handler by raising a SIGUSR2 signal which is handled
by the main thread.

Prior to waiting for a normalised event, the ERT process checks to see if it
has received a Tuxedo event.   If it has, it interprets the first event
parameter as the name of an EPM function to call and the remaining parameters
as the parameters to that function.  The ERT process then calls the
EvaluateFunction() method in its internal parser to parse and evaluate the
function.  If this fails, it logs a message including the error details from
the failed call.  The result from the function is ignored. The following
functions are handled by callback functions that are either registered in the
BuiltInSQLFunctionParser class (the ERO's internal parser is of this class),
or registered specifically in the ERT's parser (these are marked with * in the
following list, and are detailed in this document).

> biCurrencyPurge& | CurrencyPurge&  
> ---|---  
> biDerivedAttributePurge& | DerivedAttributePurge&*  
> biDerivedTablePurge& | DerivedTablePurge&  
> biFunctionPurge& | FunctionPurge&  
> biReferenceTypePurge& | ReferenceTypePurge&  
> biReferenceTypePurgeById& | ReferenceTypePurgeById&  
> biReferenceTypePurgeByLabel& | ReferenceTypePurgeByLabel&  
> biTariffPurge& | TariffPurge&*  
  
[Contents]

* * *

## Termination

During termination, the ERT process:

      1. detaches from the ERB module by calling erb_shuttingdown() then erb_detach();  


      2. detaches from the SCM;  


      3. detaches from the ACM;  


      4. detaches from the RSC;  


      5. detaches from the TEC;  


      6. detaches from the CNM;  


      7. disconnects from the database;  


      8. disconnects from the TRE; and  


      9. deallocates any dynamically-allocated memory.

[Contents]

* * *

## Commands

The following commands can be received by the ERT process:

      1. _database connect  
  
_This function connects the ERT to the database.  This command should be used
to reconnect the ERT to the database following a _database disconnect_
command._  
  
_

      2. _database disconnect  
  
_This function disconnects the ERT from the database.  This command can be
used to allow rating to continue in cache-only mode during a database upgrade.



[Contents]

* * *

## Configuration Parameters

Each ERT process is associated with a configuration item with a configuration
item type of `ERT` and a sequence number equal to the ERT process number
specified on the command-line. This configuration item stores the following
configuration parameters. These parameters are accessed by the ERT and BKR
processes.  


       * ACCOUNT_AGGREGATION_ENABLED

If the value of this integer attribute is `0` then account aggregation is
disabled. The ERT process calls the ERM::DisableAccountAggregation() method in
order to prevent the ERM from aggregating charges to accounts irrespective of
the account aggregation flag of each tariff.  This is useful for situations
where the charges generated by this ERT process are not stored into the
database.  If no value is specified for this attribute a default value of `1`
is used (that is, account aggregation is enabled by default).

       * BKR_INSTANCE

The configuration item sequence number of the BKR process that is responsible
for this ERT.

       * CHARGE_OUTPUT

The internal integer identifier of a charge output definition to be used for
constructing customised charge records.  Refer to the ERM SAS for further
details.  If no value is specified for this attribute then customised charge
records are not constructed.

       * COMMAND_LINE_ARGS

Optional command-line arguments that may be supplied by the BKR process to the
ERT process on startup.

       * ENABLED

If the value of this integer attribute is `1` the ERT process will be
automatically launched by the BKR process during startup. If no value is
specified for this attribute a default value of `0` is used.

       * GLOBAL_DA_CACHE_SIZE

The value of this attribute should be a non-zero positive integer with an
optional suffix of `M`. If the suffix is not specified (e.g. `100`) the value
is interpreted as the maximum number of global derived tables to be cached at
any given time. If the suffix is specified the value is interpreted as the
maximum amount of memory to be used by the cache (e.g. `10M` specifies a limit
of 10 Megabytes). If the ERT process attempts to store a global derived
attribute table into the cache that would cause the limit to be exceeded, one
or more of the least recently used derived attribute tables will be removed
from the cache in order to free sufficient memory for storage of the new
table. If no value is specified for this attribute then the size of the cache
is constrained only by the amount of available memory.

       * RATE_RETRY_LIMIT

If the ERT process fails during any of the following stages, it will retry a
number of times to rate the event:

         * Committing updates to rating subtotals
         * Committing updates to temporal entitlements
         * Applying charges to a balance-managed account that would cause the available credit limit to be exceeded.

The value of this integer attribute specifies the maximum number of retries.
If no value is specified for this attribute a default value of `2` is used
(for a total of 3 rating attempts per event).

       * THRESHOLD_BANDS

An EPM expression that returns a double array that contains the thresholds (in
seconds) used in the collection of threshold based statistics. The maximum
number of elements that can be specified in the array is three. Defaults to
[0.01, 0.05, 0.1].

In a later release configuration attributes may be introduced to restrict the
ERT process to a subset of all "Rating" tariffs.

[Contents]  

* * *

## Command-line Arguments

The syntax for executing the ERT process is as follows:  


> `
>
> ert <process number> [-b] [-c <freq>] [-?] [-d <debug level>]`

  
The `<process number>` argument uniquely identifies this ERT process. This
number is used to retrieve the configuration parameters for this process.

The `-b` argument allows the user to interrogate the values of expression
parser variables after each normalised event has been rated.  This flag should
be used for debugging and should not be used in normal operation.

The `<freq>` argument specifies the interval (in number of normalised events)
between writing derived attribute table cache statistics to the file
`$ATA_DATA_SERVER_LOG/ert<process number>.trc`. If this argument is not
specified, a default value of 100 is used.  Statistics are not output if the
value of the `<debug level>` argument does not include the memory usage
setting.

The `-?` argument causes a usage message to be written to stdout. The ERT
process terminates immediately.

The `<debug level>` argument is a decimal integer value or a comma-separated
list of mnemonics which controls the amount of debug information written to
the file `$ATA_DATA_SERVER_LOG/ert<process number>.trc`. The value of `<debug
level>` is interpreted by the ERT process in a similar manner to the ERM; that
is, as the sum of the following levels (in decimal):

Level | Hexadecimal | Octal | Mnemonic | Description  
---|---|---|---|---  
1 | 0x01 | 0001 | ORA | ORACLE tracing.  
2 | 0x02 | 0002 | IN | Input data debug (raw events).  
4 | 0x04 | 0004 | OUT | Output data debug (normalised events).  
8 | 0x08 | 0010 | TMO | Timeout alarms.  
16 | 0x10 | 0020 | VAR | Values of expression parser variables.  
32 | 0x20 | 0040 | EPM_LIGHT | Expression parser debug, excluding parameter values and function return values.  
64 | 0x40 | 0100 | EPM | Expression parser debug.  
128 | 0x80 | 0200 | MEM | Memory usage.  
256 | 0x100 | 0400 | ERB | Event cache tracing.  
512 | 0x200 | 01000 | DAM | Derived attribute debug.  
1024 | 0x400 | 02000 | TAR | Tariff details.  
2048 | 0x801 | 04000 | SUB | Subtotal and rating subtotal cache tracing  
4096 | 0x1000 | 010000 | ACC | Account, account cache and customer node cache tracing.  
8192 | 0x2000 | 020000 | CHG | Charge details.  
16384 | 0x4000 | 040000 | EVT | Event details.  
32768 | 0x8000 | 0100000 | SVC | Product/service details.  
65536 | 0x10000 | 0200000 | GLG | General ledger guidance details.  
131072 | 0x20000 | 0400000 | TE | Temporal entitlement details.  
262143 | 0x3ffff | 0777777 | ALL | All available tracing.  
  
For example, setting COMMAND_LINE_ARGS to "-d 32832" and "-d SVC,EPM" are both
equivalent to enabling service and expression parser tracing.

[Contents]  

* * *

## Built-in Functions

These functions are registered with the internal expression parser prior to
any expressions being evaluated.

Several additional built-in functions are provided by the ACM, ERM, RSC, TEC,
SCM, GLC and the BuiltInSQLFunctionParser.  Refer to these modules for further
details.

[Contents]

* * *

### Function ERTProcessNr&

**

Declaration**

        
                ERTProcessNr&()

**

Parameters**

None.

**Returns**

Returns the process number passed to the ERT on its command line.

**Description**

This function returns the process number of the current ERT process.  It is
used by the statistics gathering function when logging information to the
TREMON process.

**Implementation**

This function is implemented as a built-in function.  It is registered by the
ERT process so the function is only available in the rating environment.

[Contents]  

* * *

### Function ERTStats?{}

**Declaration**

        
                ERTStats?{}(MaxReset&)

**

Parameters**

MaxReset& | If TRUE (1), reset all maximum statistics.  
---|---  
  
**Returns**

Returns process statistics for the current ERT process.

**Description**

This function calls the ERMStats?{} function to obtain the process statistics.

[Contents]

* * *

### Function ERTStatsReset&

**Declaration**

        
                ERTStatsReset&(const Thresholds#[])

**Parameters**

Thresholds#[] | An array, maximum size of three, which contains thresholds used in the collection of entity statistics.  If the array is undefined, the existing thresholds are left unchanged.  If the array is defined, but empty, no threshold based statistics are collected.  
  
Refer to ERTStats?{} for explanations of the entity statistics.  
---|---  
  
**Returns**

Always returns 1.

**Description**

This function resets the statistics (which are returned by ERTStats?{}) and
sets new thresholds to be used in the collection of threshold based
statistics.

**Implementation**

This function is implemented as a built-in function.  It is registered by and
is only available in the ERT process.

[Contents]

* * *

### Function ERTTrace&

**

Declaration**

        
                ERTTrace&(DebugLevel&)
        ERTTrace&(DebugLevel$)

**

Parameters**

DebugLevel& | Diagnostic debug level in the form of an integer (eg 64 = Expression parser tracing)  
---|---  
DebugLevel$ | Diagnostic debug level in the form of a comma-separated mnemonic string (eg 'EPM,MEM' = Expression parser and Memory tracing)  
  
**Returns**

Returns 1.

**Description**

This function sets the diagnostic debug level for this ERT process to the
level specified by DebugLevel&/DebigLevel$. This value is interpreted in the
same manner as the `<debug level>` command-line argument. A value of
DebugLevel& that is less than or equal to zero (or DebugLevel$ that is an
empty string) will deactivate diagnostic tracing for the ERT process.  


**Implementation**

This function is implemented as a built-in function.  It is registered by the
ERT process so the function is only available in the rating environment.

[Contents]

* * *

### Function DerivedAttributePurge&

**

Declaration**

        
                DerivedAttributePurge&(DerivedAttributeId&)

**

Parameters**

DerivedAttributeId& | The Id of the Derived Attribute to purge.  
---|---  
  
**Returns**

Returns 1 if the Derived Attribute is successfully purged.

Returns 0 if the Derived Attribute was not found in the cache.

**Description**

This function purges derived attribute information from the ERT's Dam (Derived
Attribute cache).

**Implementation**

This function is implemented as a built-in function. Normally Derived
Attribute purges are handled by the DerivedAttributePurge& callback function
that is automatically available in the BuiltInSQLFunctionParser class (the
ERT's internal parser of this class). However, when purging derived attributes
from the ERT, there is some special handling required (making sure the
Application Environment of the Derived Attribute is Rating, and Context is
either Normalised Event or Service), so the ERT process registers its own
callback function for pugring derived attributes.

[Contents]

* * *

### Function TariffPurge&

**

Declaration**

        
                TariffPurge&(TariffId&)

**

Parameters**

TariffId& | The Id of the Tariff to purge.  
---|---  
  
**Returns**

Returns 1 if the Tariff is successfully purged.

Returns 0 if the Tariff was not found in the cache.

**Description**

This function purges the specified tariff from the ERT's internal Gtm cache.

**Implementation**

The tariff is removed from the cache via a Gtm::GetInstance()->Delete() call.
Once purged, the Tariff is immediately attempted to be reloaded back into the
Gtm. If not found, the Tariff either no longer exists at the current date/time
or has the application environment other than Rating.

[Contents]

* * *

--------------------------------------------------
## Contents

    Overview
    Related Documents
    Profiling Customers and Bill Runs
    Expected Metrics  
BGP Multiprocessing Options

    Allocation of customers to bill runs
    Choosing the best bgp multiprocessing options
    Determining the Variable Evaluation Order and Context Switches
    Impact of multiple BGP passes
    Impact of Derived Attribute Tables
    Impact of Progressive Subtotals  
Alternatives to Progressive Subtotals

    Logs and traces required for performance analysis
    Sample execution scripts
    Tools for examining traces
    Performance Reference

    Where to start looking if you're not getting benchmarked performance
    Some useful bgp tracing options
    How to determine what's causing extra bgp passes
    Feature comparisons between V3, V4, V5 and why later versions are better
    V4 Customer Batches
  

* * *

## Overview

BGP performance depends a a large number of factors.  Becoming a tuning guru
takes time and requires a broad level of skill.  Fortunately, it's not
necessary to become a tuning guru in order to achieve reasonable BGP
performance.  This document is aimed at giving some guidance to those that
require it.

Further detail can be obtained by reading the Architecture Document for the
BGP, in particular the following sections.

    Configuration Details
    Initialisation
    Context Processing
    Multiple Processes

This guide has a current focus of CB3.  General concepts are also relevant to
later versions of CB.  Some specific comments on features of later versions
are included (and more will be included over time).  Major billing
enhancements are included in CB4 which improve the biller's operational
capability.  Single guide point mutli-processing has been added to this
document, a feature of 4.00.14 and later releases.

Return to contents.

* * *

## Related Documents

    Architecture Document for the BGP

* * *

## Profiling Customers and Bill Runs

Prior to performing any tuning it is necessary to gather profiles of the
services, customer nodes, customer hierarchies, and bill runs.  A rough method
is to sample the rating charges produced for a typical month of operation.
This will not be applicable for all customers or during all months of the year
but will serve as a reasonable starting point.  A more exact method of tuning
requires sampling the unbilled charges immediately prior to commencing the
bill run and choosing BGP options accordingly, however gathering these samples
and performing the analysis is operationally expensive and typically runs will
not change dramatically from month to month to justify the expense.

As multiple queries are required over the profiles it is best to store the
aggregated results in temporary profiling tables.  In Oracle 8i and above
these tables could instead be materialised views.

The charge table is used to gather statistics as this contains the service id.
In a typical configuration there will be one charge per normalised event
produced during rating.  This is not alway the case and should be verified
from the counts output on BGP termination.

### Profiling Tables

NOTE 1: Profile start and end dates should be adjusted for a typical month of
operation.

NOTE 2: These queries will need to be adjusted if the unbilled charged
associated with a specific bill run are required.  The profile start and end
dates will need to reflect the bill run being examined.  In this case, the
data collected for services in other runs will be incorrect as they would not
contain a full cycle of unbilled charges.

        
                def profile_start_date = '23-JAN-2002'
        def profile_end_date = '23-FEB-2002'
        
                create table SERVICE_PROFILE
            tablespace ATA_SERVICES nologging 
            as
            (select service_id, 
                    count(*) charge_count
               from charge
              where charge_date between to_date(&profile_start_date, 'dd-mon-yyyy') 
                and to_date(&profile_end_date, 'dd-mon-yyyy')
                and customer_node_id is null
              group by service_id)
        
                create table CUSTOMER_NODE_PROFILE
            tablespace ATA_CUSTOMER nologging 
            as
            (select s.customer_node_id, 
                    count(s.service_id) service_count, 
                    count(psf.service_id) active_service_count, 
                    sum(psf.charge_count) charge_count
               from service_history s, service_profile sp
              where sysdate between s.effective_start_date and s.effective_end_date
                and s.service_id = sp.service_id (+)
              group by s.customer_node_id)
        
                create table CUSTOMER_PROFILE
            tablespace ATA_CUSTOMER nologging 
            as
            (select nvl(cnh.root_customer_node_id, cnh.customer_node_id) customer_node_id, 
                count(*) node_count,
                sum(cnp.service_count) service_count, 
                sum(cnp.active_service_count) active_service_count, 
                sum(cnp.charge_count) charge_count
            from customer_node_history cnh,
                customer_node_profile cnp
            where sysdate between cnh.effective_start_date and cnh.effective_end_date
            and cnh.customer_node_id = cnp.customer_node_id (+)
            group by nvl(cnh.root_customer_node_id, cnh.customer_node_id))
        
                create table SCHEDULE_PROFILE
            tablespace ATA_DATA nologging 
            as
            (select cnh.schedule_id,
                count(*) customer_count,
                sum(pcf.node_count) node_count,
                sum(pcf.service_count) service_count, 
                sum(pcf.active_service_count) active_service_count, 
                sum(pcf.charge_count) charge_count
            from customer_node_history cnh,
                customer_profile pcf
            where sysdate between cnh.effective_start_date and cnh.effective_end_date
            and cnh.customer_node_id = pcf.customer_node_id
            group by cnh.schedule_id)

### Bill Run Profile

        
                select s.schedule_name, 
               decode(s.start_repeat_type_code, 
                   1, 'Month', 2, 'Month', 3, 'Month', 4, 'Month', 
                   5, 'Week', 6, 'Day', 'Other') "TYPE", 
               s.repeat_units "UNITS", 
               to_char(s.first_date, 'dd-mm-yyyy') first_date, 
               to_char(s.effective_date, 'dd-mm-yyyy') effective_date, 
               decode(s.schedule_status_code, 1, 'Active', 2, 'Complete') status, 
               psf.*,
               s.general_1 "BGP Options"
          from schedule_profile psf, schedule s
         where s.schedule_id = psf.schedule_id (+)
           and s.schedule_task_type_id = 11
         order by schedule_name

### Customer Profile (by schedule)

        
                select * 
          from customer_profile
         where customer_node_id in (
               select customer_node_id 
                 from customer_node_history
                where schedule_id = (
                      select schedule_id from schedule
                       where schedule_name = ?))
         order by nvl(charge_count, 0) desc

### Customer Node Profile (by customer)

        
                select * 
          from customer_node_profile
         where customer_node_id in (
               select customer_node_id 
                 from customer_node_history
                where root_customer_node_id = ? or
                      customer_node_id = ?)
         order by customer_node_id desc 

### Service Profile (by customer node)

        
                select * 
          from service_profile
         where service_id in (
               select service_id 
                 from service_history
                where customer_node_id = ?)
         order by charge_count desc

* * *

## Expected Metrics

These metrics are based on an EICP V3 configuration using tax model 2 with
some additional customer configuration.  Two passes are required over the
events and charges.

**NOTE: Actual results can vary dramatically based on the customers
configuration and the number of passes required.   Refer to the _EICP report_
for configuration and platform comparisons.**

These metrics are taken from a Sun UltraSPARC-III/750MHz 8cpu 16GB memory.

### Throughput

These throughputs are per bgp and assume multiprocessing is being performed at
an appropriate level.  The rates are proportional to the number of bgps
provided multiprocessing is being performed at the correct context to keep all
bgps busy.   Runs that include customers with different types of profiles will
have difficulty in keeping all bgps busy for the entire run (hence should be
split into separate runs to achieve the best results).

NOTE: The table below shows multi-processing metrics.  The customer and
service rates can be doubled for single-streams containing low service and
event volumes per customer.

**Events** Based a high number (>100,000) of events per service. | 55 events / second | 18 ms / event  
---|---|---  
**Services** Based on a low number (1 or 2) charges per service, high number of services per node (1000). | 7 services / second | 140 ms / service  
**Customers** Based on a large number of consumer/residential type hierarchies (>1000), low number of nodes (1 or 2) per hierarchy, low number of services per hierarchy (1 - 5), low number of charges per service (< 1).  Total throughput was 500 ms / hierarchy, less 4 services at 140 ms / service and there is no overhead at all.  All the time is in the services. This throughput includes 4 calls to biSQLQueryRW in the trerwdb service per customer (1 for each customer node and one for each service to obtain the tax exemptions).  A heavier configuration resulted in an additional 18 calls to biSQLExecute (trerwdb) and 15 calls to biSQLQuery (trerodb) per customer (at the customer node context).  These calls resulted in additional 750ms / hierarchy.  | (Limited by the number of services) | < 10 ms  
**Tax Calculation** For Model 1 Taxation, the CommTax module is called per event and can use multi-processing.  For Model 2 Taxation, the CommTax module is called per node this is single stream for each node. | 220 calls / second | 5 ms / call  
  
### **Memory**

**Overhead** Each bgp requires an overhead to store referenced variables. | 150 MB  
---|---  
**Events** Event and charge information is not cached per event.  Charges generated are written directly to the database and re-retrieved as required. | 0  
**Services** Service information is cached for use in subsequent passes over
the services.  This memory is progressively released for each service during
the final pass.  Hierarchies with a large number of services (> 10,000) will
require multiprocessing at the customer node or service context in order to
keep the memory per bgp below the machine limit.  Hierarchy sizes are limited
by total available memory (including swap space).  
  
An appromation of the theoretical minimum memory used per parser per service
(or customer node) would be:

> 72 + [total functions] * 4 + [total variables] * 4 + [used functions] * 100
> + [used variables] * 48 + [variable string, hash and array assignments]

Based on a high number of services per node, low number of charges, single hierarchy A non-typical configuration with 5000 unnecessary derived attributes with an application environment of 'rating' averaged 80 kbytes / service. | 50 kbytes / service  
**Customers** Based on a high number of hierarchies, low number of nodes, services and charges. The set of products on each node is used to create a variable evaluation order for that node.  This evaluation order is retained for use on subsequent nodes.  Bill runs containing similar sets of products on each node allow greater reuse and hence less memory growth.  Investigations on production hierarchies show varying results.  One run contained 100 evaluation orders for 3000 nodes and a total memory growth of 800 MB.   Other runs on 10,000 and 100,000 hierarchy runs showed much greater reuse and a total memory growth to only 400 MB. Each evaluation order uses on average approx (800 MB / 100) = 8 MB. | 8 MB / hierarchy product set combination  
  


* * *

## BGP Multiprocessing Options

The BGP can multiprocess at the customer, customer node, service and sub
serivce levels.  When the bgp is operating in multiprocess mode there is a
parent bgp and a number of child bgps.

Whilst a combination of all modes (or even a couple of modes) is possible it
is not recommended as all processes will be consuming memory but only a
portion of these will be performing any real work.  There will also be
additional interprocess communications up to the controlling bgp that must
pass through the intermediate layers.

In CB4 and above, billing priorities should be assigned.  Processing times
referred to the the following bullet points are estimated times calculated
using the tables above.

       * when using customer level multi-processing, all customers should be assigned a billing priority if their processing time is greater than 25% of (the bill run processing time / multi-processing level)
       * when using node level multi-processing, all customer nodes in a hierarchy should be assigned a billing priority if their processing time is greater than 25% of (the processing time of the hierarchy / multi-processing level)
       * when using service level multi-processing, all services under a node should be assigned a billing priority if their processing time is greater than 25% of (the processing time of the node / multi-processing level)

BGP multiprocessing is at its optimal when processing bill runs containing
similar customer profiles.  Refer to Allocation of customers to bill runs for
further advice.

### Customer (-c Cw)

Using this mode there is a controlling bgp process and w child bgp processes.
Each bgp processes a single customer at a time.  Once a customer has finished
being processed it notifies the controlling bgp by returning a completion
message.   The controlling bgp then sends a message back to the child bgp
informing it to start processing the next customer.

This mode is applicable for

       * A moderate to large number of customers.

### Customer Node (-c Nx)

Using this mode there is a controlling bgp process and x child bgp processes.
The controlling bgp processes a single customer at a time.  For each customer,
nodes in the hierarchy are allocated to the child bgps.

Once a Customer Node child process has completed processing the current
hierarchy pass of a customer node it notifies the parent process by returning
a completion message.   The parent process then sends a message back to the
child informing it to either start processing the next customer node or
process the next hierarchy pass of a customer node it processed earlier.  All
nodes must be processed before commencing the next hierarchy pass or
continuing to the next customer.

Customer Node processes are forked at the start of a bill run and remain alive
for the duration of the run. If multiple customers are being processed then
the child process will not terminate until after the last customer is finished
being processed.

This mode is applicable for

       * A small number of customers with a moderate to high number of nodes, a moderate number of services and any number of events.

NOTE: You will probably want to configure a number of bgps equal to the number
of cpus.   Depending on configuration this may lead to inefficient use of the
cpus.   Currently a customer hierarchy can only be efficiently processed by up
to 12 bgps.   The level of interprocess communications required between the
child bgp process and the controlling bgp restricts multiprocessing at
customer node and service contexts to 8 - 12 bgps utilising 100% of a cpu.
Increasing the number of bgps beyond this point (necessary for processing some
very large hierarchies) will result in a lower cpu utilisation per bgp.
Raising this limit is the subject of medium ticket SPR#43400.  To add
perspective, with CB3 throughputs, high volume runs containing 10,000,000
events can be processed by 8 cpus in 8 hours and large hierarchy runs
containing 1,000,000 services and no events can be processed in 5 hours.  You
may configure a number of bill runs in parallel.

### Service (-c Sy)

Using this mode there is a controlling bgp process and y child bgp processes.
The controlling bgp processes a single customer, single customer node at a
time.  For each customer node, services of that node are allocated to the
child bgps.

Once a Service child process has completed processing the current hierarchy
pass of a service it notifies the parent process by returning a completion
message.  The parent process then sends a message back to the child informing
it to either start processing the next service or process the next hierarchy
pass of a service it processed earlier.   All services on a node must be
processed before continuing to the next customer node.   All nodes must be
processed before commencing the next hierarchy pass or continuing to the next
customer.

Service processes are forked at the start of a bill run and remain alive for
the duration of the run. If multiple customers are being processed then the
child process will not terminate until after the last customer is finished
being processed.

This mode is applicable for

       * A small number of customers with a small number of nodes and high number of services per node and any number of events.

### Sub Service (-c Ez)

Using this mode there is a controlling bgp process and z child bgp processes.
The controlling bgp processes a single customer, single customer node, single
service at a time.  For each service, a range of events are allocated to the
child bgps.  Ranges may be delineated by a specified number number of days or
hours.

Once a Sub Service child process has completed processing the current
hierarchy pass it notifies the parent process by returning a completion
message.  The parent process then sends a message back to the child informing
it to either start processing the next range or process the next hierarchy
pass of a range it processed earlier.   All events of a services must be
processed before continuing to the next service.   All services and nodes must
be processed before commencing the next hierarchy pass or continuing to the
next customer.

Sub Service processes are forked at the start of a bill run and remain alive
for the duration of the run. If multiple customers are being processed then
the child process will not terminate until after the last customer is finished
being processed.

Sub service processing contains the concept of an event threshold, a minimum
number of events that a service must contain in order to be processed by sub
service processes. If this threshold is not exceeded then the service is
processed by the context that has spawned sub service processes (CUSTOMER,
NODE or SERVICE).  The evaluation of this threshold (and the minimum event
range) is performed for each service during processing of the service context
hence is not multi-processed at the sub service level.  This can be observed
by low cpu utilisation at the commencement of processing for each service in
the first bgp pass.  To some extent, this overhead can be balanced by using a
combination of multiprocessing levels, however such combinations (node and
service levels only) result in imbalance of processing in the subsequent
passes due to overheads of the threshold queries in the first pass.  Compared
with the duration of the bill run, this overhead is small and is far
outweighed by the benifits of sub service multi-processing.

This mode is applicable for

       * A small number of customers with a small number of nodes and a small number of services per node and a very high volume of events.
       * Single service event volumes that are are greater than the total number of events on the customer divided by the number of cpu's available for processing.

### Customer, Customer Node and Service (-c Cw -c Nx -c Sy -c Ez)

Using this mode there is 1 controlling bgp, w customer child bgp processes,
w*x customer node child processes, w*x*y service child processes and w*x*y*z
sub service child processes.

When multiprocessing at multiple contexts, the multiprocessing for a single
context works as described above.  Multiprocessing at multiple contexts
communicate through chains of parent and child bgps.

The major drawback when using combinations of modes is that all hierarchies
will be processed by splitting customers, customer nodes and services to their
respective child bgps.  When the numbers of customers, customer nodes or
services are small this is an unnecessary and expensive processing overhead
when compared to multiprocessing at a single context.

Customers should be allocated to bill runs in order to avoid the need to
multiprocess at multiple contexts.  It is preferable to have multiple parallel
runs.

This mode is applicable for

       * Mode combinations are rarely applicable except for badly laid out bill runs containing a combination of customer profiles.

* * *

## Allocation of customers to bill runs

Customers should be allocated to bill runs in order to maximise utilisation of
available cpu and minimise memory requirements.

Ideally there are four profiles of customer.

       * Residential / Medium Corporate
       * Large Corporate / Wholesale
       * High Volume Services
       * Very High Volume Services

These profiles roughly correspond to the contexts where multiprocessing can be
performed (customer, customer node, service, event).  Event level
multiprocessing (also known as Sub Service multiprocessing) was added in
4.00.14.

In the case of a single customer including more than one of these profiles,
one should be selected as the dominant profile with the aim of keeping all
bgps processing at 100% for the duration of the run.

For the purposes of choosing a dominant profile, and allocating customers to
bill runs, hierarchy sizes and volumes are relative rather than absolute.
Processing times are absolute (assuming optimal multiprocessing) and are
detailed in Expected Metrics.

Bill runs are typically scheduled during periods of low CSR usage (such as
overnight or weekends).  The default implementation is for sequential bill
runs.  This assumes that the profile of customers on each bill run allow the
use of all available cpus.   Where bill runs are not able to use all available
cpus, they may be configured to run in parallel.  This is controlled by the
Maximum Tasks field of the schedule type "Invoice Generation".

In  CB3, it is recommended that a bill run consist of a single profile of
customer only to make optimal use of multiprocessing options.  With care it is
possible to combine customers with differing profiles into a single bill run
and still retain optimal multiprocessing throughputs.  This could be done for
the purposes of reducing the number of bill runs to reduce decision making
process when allocating customers to bill runs.  It could also be done to
increase the size of a single bill run to make use of all available cpus.

CB4 billing enhancements provide a number of operational enhancements
including a bill run entity, billing configuration, billing priorities.  In
addition, the bgp process is a tuxedo service.  The billing configuration
identifies a distinct set of bgps with mutliprocessing options preconfigured.
Each customer can be identified with a billing configuration.  This means that
different profiles of customers can be assigned to a single bill runs and
still be processed efficiently.   Billing priorities allow each customer,
customer node, and service to be processed in an assigned priority order.  Use
of tuxedo services provides the mechanism for assigning customers to different
sets of bgps.  Each distinct set of bgps are contolled by separate tuxedo
services.  In CB4 it is more important to understand some of the memory
implications associated with this new behaviour.

### Memory Implications for CB4 Billing

When multiprocessing not used, the trebgp process is not restarted between
runs, and consequently does not release and memory used.  Consequently,
multiprocessing should be used for customers containing anything move than a
small number of services (> 1000), due to the memory overhead of the
persistent service contexts.

### Combining profiles on a single bill run

When combining customers with differing profiles onto a single bill run, the
aim is to retain multiprocessing at the highest of the two contexts

#### Combining residential and corporate profiles

A residential profile has a small number of customer nodes per customer
(typically 1-3), a small number of services (typically 1 - 5), and a low event
volume (typically < 200 events).  This profile is best multiprocessed at the
customer context.

If we add a single corporate into this run it will be processed using a single
bgp.   The maximum size of this corporate is controlled by two separate
limits.

The first of these limits is the processing time of the corporate compared to
the processing time of the sum of the residentials.  The residential customers
should occupy the remaining bgps for the duration of the run.  This limit also
assumes that the bgp starts processing the corporate at the start of the run.
The customer ordering can be controlled by passing an order by clause as a bgp
option.  This situation obviously has its complexities but it can be done.
More preferably, the proportion of residential to corporate should be much
higher.

The second of these limits is the number of services that can be processed by
a single bgp.  Each service occupies on average 50 - 100 kbytes (this is
configuration dependent).  For performance reasons this is retained for the
duration of processing of the hierarchy.  The maximum process memory varies
per platform.  For Solaris this is 3.75 GB, for HP-UX this is 960 MB, for AIX
this is 750 MB.  Hence hierarchies with more than 5,000 services would need to
be split across multiple child bgps.

The first limit (processing time) would likely be hit before the second limit
(memory).

If a larger number of corporate hierarchies were added into the run, say at
least 1 per bgp, and those hierarchies had similar processing times, and they
could be forced (using the order by option to the bgp) to start before the
residential customers, then they could satisfactorily be combined with
residential customers.  In this case the second limit above is more important.

#### Combining residential and high volume profiles

This combination is similar to combining residential and corporate profiles.
Attention should be paid to the relative processing times and the processing
order of the hierarchies.

* * *

## Choosing the best bgp multiprocessing options

General Guidelines

       * multiprocess at the highest context possible (to reduce interprocess communications)
       * use the fewest bgps possible (in order to achieve full cpu utilisation for the entire run and conserve memory)
       * limit the use of multiprocessing at multiple contexts (special cases only)
       * multiprocess to reduce the memory use of a single bgp
       * with careful monitoring, improvements in performance may be gained by overloading the number of bgps (up to twice the number of cpu's) in order to squeeze the I/O and operating system scheduling performance.

Refer to Per-Process Data Segment Limit for operating system specific limits.

### Residential / Medium Corporate

Bill runs for residentials and medium corporates contain a large number of
customers in each run and low service and event volumes.  As such,
multiprocessing should be performed at the customer context.  With this
context, each bgp should be able to keep a cpu 100% utilised (apart from any
switching to oracle child processes, and any tre processes required by the
configuration).

Multiprocessing Recommendation: Customer context.  Up to one bgp per cpu.

### Large Corporate / Wholesale

Bill runs for large corporates contain a small number of customers in each
run.   Profiles for this type of customer will range from a high number of
nodes with few services to a low number of nodes with many services.  Total
services will be in the 100,000's.

For hierarchies with a large number of nodes (>40) and a reasonable
distribution of services, multiprocessing should be at the customer node
context.  The minimum number of bgps required is based on the memory usage of
each bgp and the Per-Process Data Segment Limit.  Memory usage is impacted by
configuration.  (Refer to Impact of multiple BGP passes.)  Providing there is
a reasonable distribution of services, each stream should be able to keep a
cpu fully utilised.

For hierarchies with a small number of nodes (<20) or a poor distribution or
services, multiprocessing should be at the service context.

Hierarchies falling between these two extremes may benefit from
multiprocessing at multiple contexts.  For multiprocess calculations, use the
total number of service context bgp child processes.  (Refer to BGP
Multiprocessing Options)

### High Volume Services

Bill runs for high volume services contain a small number of services and high
event volumes on each service (100,000 - 1,000,000).

For runs with a single high volume service per customer, multiprocessing
should be at the customer context. The number of bgps should be limited by the
smallest of the number of available cpus or the number of customers in the
run.

For hierarchies with multiple nodes and a single high volume service per node,
multiprocessing should be at the customer node context.  The number of bgps
should be limited by the number of available cpus.  If the number of active
nodes per customer is less than the number of available cpus, a combination of
customer and node level multiprocessing should be used.

For single hierarchies with multiple high volume services on a single node,
multiprocessing should be at the service context.  The number of bgps should
be limited by the number of available cpus or the number of services in the
run.

NOTE: Where the number of services in the run is small and contain an unequal
distribution, it may be preferable to decrease the number of cpus in order to
achieve a level cpu and i/o load for the duration of the run, thus making
other cpus available for other tasks.  In CB4, a priority can be associated
with individual services to ensure the large ones are allocated first.

### Very High Volume Services

Bill runs for very high volume services contain a single services with very
high event volumes (> 1,000,000).

These runs will benefit from event level multiprocessing being made available
in CB4 to selected customers.

To give some perspective, high volume runs containing 1,000,000 events can be
processed by one 8 cpus in 7 hours using a single bgp.

* * *

## Determining the Variable Evaluation Order and Context Switches

The bgp process has an option to output an explanation of the variable
evaluation order for each  
customer. No invoices are generated with this option.  The plan is output for
customers that have not yet been invoiced for this task.  Consequently, the
typical scenario is to select a pending task or a task on which invoices had
been revoked.

`bgp -x -q <task queue id> > bgp.plan`

Context switching information is also included in this output and is key to
optimising a configuration.

The ordering algorithm attempts to order as much as possible as quickly as
possible based on the interdependencies among variables and the contexts of
the variables.

* * *

## Impact of multiple BGP passes

Customers are processed sequentially.  For each customer the BGP traverses a
number of contexts and evaluates variables whilst in each context.  A context
may be traversed a multiple times due to variable interdependencies.

BGP contexts are grouped into persistent contexts and non persistent contexts.
Persistent contexts are those contexts where the parsers retain their state
between context changes, these are CUSTOMER, CUSTOMER_NODE and SERVICE.
Nonpersistent contexts are those whose parsers are flushed when a context
change occurs, these are, NORMALISED_EVENT and CHARGE.

For the purpose of this guide, a _pass_ is where the BGP processes each
context from CUSTOMER down to CHARGE and returning to CUSTOMER.  

### Database Reads and Writes

Multiple passes require the NORMALISED EVENT and CHARGE records to be
retrieved from the database multiple times.

During the first pass, events and rating charges are read from the database
and any billing charges generated in the first pass are written to the
database.

During subsequent passes, events, rating charges and billing charges generated
from earlier passes are read from the database.  Subsequent passes will take
longer due to the addition of billing charges.

Reducing the number of passes from three (3) to two (2) will typically improve
throughput by 30 - 40%.

### Memory used by persistent contexts

Persistent service contexts are flushed as each service is processed in the
final pass.   Where more than one pass is required the contexts of all
services in a hierarchy are retained within the bgp child process that
processed that service.

Each service context will consume anything from 50 kbytes to 100 kbytes.  The
addition of large hashes (such as tax model 2 hashes and reporting hashes)
will increase the size of each context.

If large hashes are required the configuration should be optimised so that
those hashes (or at least the large terms of those hashes) are populated in
the final pass.  In some situations, hashes populated in earlier passes may be
forcibly flushed (by undefining the hash) providing those hashes are also
finalised (ie. their values are used) in the earlier pass.



* * *

## Impact of Derived Attribute Tables

A large number (> 1000) of additional derived attribute tables are used for
some customer configuraitons.  Tables with an application environment of
'Rating' are preloaded in various degrees for both rating and billing.
Typically these additional tables are referenced using DerivedTableLookup
functions which don't require an application environment of 'Rating'.
Configuring these tables with an application environment of 'TRE Table'
results in both memory and performance savings.

For rating prior to CB 4.00.10, performance degrades linearly with the number
of rating tariffs and DAs configured.  For a typical template configuration
(600 DAs, mostly rating, CB 4.00.10 has double the rating performance of
4.00.09 and earlier).

For rating, memory utilisation and startup time are impacted by the number of
Rating DA's configured.  The recommendation is to switch all unnecessary
Rating DA's to TRE Table.  There will be an initial performance hit the first
time the TRE Table DA is used as it is loaded on demand.  The SIL check
script, `checkk_app_env` checks specifically for this case.

For billing, variable references are kept on a per service basis.  Each
reference is 4 bytes.  Each 1000 variables (with rating and billing
application environments) thus occupy 4 kbytes per service retained for the
duration of processing the hierarchy.

* * *

## Impact of Progressive Subtotals

Progressive subtotals are typically used for implementing free minutes and
volume event rating.  These types of tariffs are targetted at residential
customers or medium corporate hierarchies which don't require multiprocessing
below the customer context.

Progressive subtotals result in prohibitiing multiprocessing below the
subtotal context within the BGP pass where the subtotal is referenced (and
evaluated).  For example, if Customer level progressive subtotals are used
then the capability for Customer Node, Service, and Event level parallelism
for those passes performing the evaluation is lost, but other passes can be
parallelised..

Progressive subtotals are inappropriate for large corporate hierarchies,
wholesale services, and high volume services.  Refer to the next section for
alternatives.

Implementations containing a mix of customer profiles should be selective in
the use of progressive subtotals.  Selectivity is controlled by the assignment
of subtotals to products.

Ideally, there should be completely separate products setup for high volume
services. For high volume services, you really want to avoid any progressive
subtotals and disable outputting of event details in the invoice image
(remember we don't have any support to parallelise the generation of an
invoice image). Replace the event details with some (much more useful) summary
information (eg. summary by day of week, hour of day, call destination, etc).

Refer to Progressive Subtotals in the BGP SAS for further details.

* * *

## Alternatives to Progressive Subtotals

Progressive totals are typically used for volume event rating and free
minutes.   They are inappropriate for large corporate hierarchies, wholesale
services, and high volume services.  Refer to the previous section for the
impact of progressive totals.

Alternatives to progressive subtotals are

       * Apply bulk discounts
       * Rating subtotals
       * Course grained subtotals 

### Apply bulk discounts

Don't attempt to incorporate 'progressive' discounts into each event's final
charge - just calculate and display bulk discounts at the end for each
service/node/customer. The answer (final invoice amount) can of course still
be similar (although not necessarily the same for all configurations). This is
in my opinion the safer option, but it of course is not transparent.

### Rating Subtotals (available in CB 4.02)

Rating subtotals essentially allow the pushing of some of the billing
configuration into rating.  This introduces a requirement for events to be
rated in order which is only practical if the client is doing real time or
near real time rating, and also that re-rating must be single stream). It can
also simply shift the scalability problems from billing to rating.

If rating performance is critical, then a high percentage of the rating
subtotals values should be in the rating subtotal cache.  For a simple
configuration, rating subtotals could handle up to 1.2 million customers.  For
a more complex configuration, 500k customers.

Free Directory Assistance calls are a good candidate for Rating Subtotals -
because directory assistance calls are likely to be a small percentage of any
service's overall set of calls, they are unlikely to have any impact on rating
concurrency. You still need to rate calls in order though.

### Course grained subtotals

For volume event rating, you can use a hash subtotal (or subtotals) to
sumarise call details by the hour (even down to the minute if you wanted), and
then apply volume event rating (and discounts) across the hourly (or minute)
aggregates. You could then re-rate the calls using these hash subtotals if you
really wanted to.

A similar technique can be applied to free minutes.

Since this doesn't use any progressive subtotals, it can be fully
parallelised. But of course it won't give exactly the same answer as using
standard volume event rating on each event.

If you wanted to use the same product(s) for your low volume and high volume
services (which is not recommended), but use standard volume event rating for
the low volume, and 'coarse grained' volume event rating for your high volume,
then you could setup a rating subtotal to simply count the number of events in
the month for the service/customer (this has no rating concurrency issues and
imposes no processing restrictions on rating) and then based on that value
dynamically switch behaviour of the hash subtotal to per event or 'coarse
grained' - 10,000 events would probably be a reasonable threshold.

* * *

## Logs and traces required for performance analysis

### Machine Specifications

This is reqired for the operating system version and number of cpus.

`uname -X`

### Log.out

This is required to determine run start and completion times, metrics and
process ids.

### Task Result

This is useful for determining rates of invoice processing for small
hiearchies.

### Cpu Utilisation

Output from tools such as sar at 60 second intervals.

### Process Utilisation

Output from tools such as top and ps at 60 second intervals.

        
                top -n
        ps -ef

### I/O Utilisation

Output from tools such as iostat at 60 second intervals.

### Tuxedo Service Utilisation

Output from tmadmin for selected TRE services.

        
                tmadmin <<EOF 2>/dev/null >> tmadmin.stats &
        printservice -s biCommTax
        printservice -s biSQLQuery
        printservice -s biSQLExecute
        printservice -s biCommand
        EOF

### BGP Variable Evaluation Orders

Run the biller to determine the variable evaluation order.

`bgp -x ... > bgp.plan`

### BGP Traces

Run the biller with debug options phase and memory tracing.

        
                bgp -d PHA,MEM ...

The traces will be created in the $ATA_DATA_SERVER_LOG directory.

### Oracle Traces

Oracle utilisation statistics.

At the beginning of the run.

        
                cd $ORACLE_HOME/rdbms/admin
        sqlplus system @utlbstat

At the completion of the run.

        
                sqlplus system @utlestat

The statistics will be output to the report.txt file in the current directory.

* * *

## Sample execution scripts

### Run.sh

        
                #!/bin/sh
        echo Starting Stats
        sh ./gather.sh &
        
        task_queue_id=123456
        multiprocessing_options="-c C<x> -c N<y> -c S<z>"
        debug_options="-d PHA,MEM"
        
        echo Revoking invoices...
        revoke_invoices -q $task_queue_id
        
        echo Generating bill run plan...
        bgp -x -q $task_queue_id > bgp.plan
        
        echo Starting bill run...
        bgp -d $debug_options $multiprocessing_options -q $task_queue_id
        
        echo Stopping Stats
        ps -ef|grep gather|grep -v grep|awk '{ print $2 }'|xargs kill

### Gather.sh

        
                #!/bin/sh
        echo Gathering stats...
        while [ 1 = 1 ]
        do
           date
           sar 10 6 >> sar.stats &
           date >> ps.stats
           ps -ef >> ps.stats &
           date >> top.stats
           top -n >> top.stats &
           date >> iostat.stats
           iostat 2 4 >> iostat.stats &
           date >> buffer.stats
           sqlplus / @../buffer_cache.sql 2>&1 >> buffer.stats &
           date >> tmadmin.stats
           tmadmin <<EOF 2>/dev/null >>tmadmin.stats &
        printservice -s biCommTax
        printservice -s biSQLQuery
        printservice -s biSQLExecute
        printservice -s biCommand
        EOF
           sleep 60
        done

* * *

## Tools for examining traces

### Countbytes.pl

        
                #!/usr/bin/env perl
        #
        # File: countbytes.pl
        # Description: Used for counting bytes from hash compaction.
        # Usage: cat bgp.trc | fgrep Compact | perl countbytes.pl
        
        my $keycount = 0;
        my $count = 0;
        my $line;
        
        while (<>) {
            if (/bytes/) {
                $line = $_;
                $_ =~ /(\d+) bytes/;
                $count = $1;
                print $line if $count > 10000;
                $keycount += $1;
            }
        }
        print "Total bytes = " . $keycount . "\n";
        
        exit 0;

### Countkeys.pl

        
                #!/usr/bin/env perl
        #
        # File: countkeys.pl
        # Description: Used for counting hash keys
        # Usage: cat bgp.trc | fgrep Hash | perl countkeys.pl
        
        my $keycount = 0;
        my $count = 0;
        my $line;
        
        while (<>) {
            if (/keys/) {
                $line = $_;
                $_ =~ /(\d+) keys/;
                $count = $1;
                print $line if $count > 10000;
                $keycount += $1;
            }
        }
        print "Total keys = " . $keycount . "\n";
        
        exit 0;

* * *

## Performance Reference

    Very High Volume
    High Volume
    Large Hierarchy
    Large Number of Small Hierarchies, Small Volumes

* * *

### Very High Volume

1 customer, 13 nodes, 5,000 services, 350 active services, 6,300,00 events.  
1 node carrying almost all the events, with the high volumes dispersed over 30
services on the node.  
Largest service has 500,000 events.  
Configuration uses two passes.

The large service results in 320,000 tax keys.  
Final hash contained 1,400,000 tax keys.

BGP Options: | S12  
---|---  
Duration: | approx 10 hours  (prorata estimate)  
Throughput: | 6,300,000 events / 10*60*60 seconds = 175 events / second  
6,300,000 events / 10*60*60 seconds / 12 bgps = 14 events / second / bgp  
Memory: | BGPs used between 200 and 500 MB  
Comment | The profile of services on the node did not allow for equal use of all bgps.  All bgps were contending for cpus during the first third of each pass.   During the last half of each pass, only one bgp was operating.  
The test machine had 8 cpus.  
  


BGP Options: | S4  
---|---  
Duration: | 11 hours  
Throughput: | 6,300,000 events / 11*60*60 seconds = 160 events / second  
6,300,000 events / 11*60*60 seconds / 4 bgps = 40 events / second / bgp  
Memory: | None available  
Comment | The profile of services on the node did not allow for equal use of all bgps.  The number of events processed by each bgp were 2.3 million, 1.2 million, 1.2 million, 1.6 million respectively.  CPU processing time was 286 minutes, 203 minutes, 220 minutes, 382 minutes respectively.  Note that the bgp that processed the largest number of events did so using less time than the next largest number of events.  This reflects in the order the services are allocated to the bgps.  High volume services allocated late in the cycle will produce this result.  (CB4 allows prioritised allocations of customers, nodes and services to reduce this impact.)  An ideal profile would have seen about 55 events / second / bgp.  
  
* * *

### High Volume

1 customer, 5 nodes, 444 services, 38 active services, 214,645 events.  
1 service carrying almost all the events.

BGP Options: | None  
---|---  
Duration: | 14 minutes  
Throughput: | 214,645 events / 14*60 = 255 events / second   
Memory: | 200 MB per BGP  
  
* * *

### Large Hierarchy

100 nodes, 100,000 services, 10,000 active services, 200,000 events  
1000 services per node, 80-300 active services per node.  
Largest service has 6,500 charges.  
14 services have > 1,000 charges.  
Average 2 events per service.  Average 20 events per active service.

BGP Options: | N12  
---|---  
Duration: | 26 minutes  
Throughput: | 200,000 events / 26*60 = 128 events / second  
Memory: | 750 MB per BGP  
  


BGP Options: | N8  
---|---  
Duration: | 30 minutes  
Throughput: | 200,000 events / 30*60 = 111 events / second  
Memory: | 1061 MB per BGP  
  


BGP Options: | N4  
---|---  
Duration: | 54 minutes  
Throughput: | 200,000 events / 54*60 = 62 events / second  
Memory: | 1844 MB per BGP  
  


BGP Options: | S8  
---|---  
Duration: | 1 hour  
Throughput: | 200,000 events / 1*60*60 = 55 events / second  
Memory: | 1001 MB per BGP  
  
Each service uses on average approx (1,000MB / (100,000 / 8)) = 80k

* * *

### Large Number of Small Hierarchies, Small Volumes

3000 hierarchies, 1 node per hierarchy, 1-5 services per node, 1 event per
service.

BGP Options: | None  
---|---  
Duration: | 14 minutes (including 2 minutes to initialise)  
Throughput: | 3,232 hierarchies / 12*60 = 4.5 hierarchies events / second   
Memory: | 800 MB per BGP  
Comments: | Light configuration (see below).   
  


BGP Options: | C8  
---|---  
Duration: | 6 minutes (including 3 minutes to initialise)  
Throughput: | 3,232 hierarchies / 3*60 / 8 bgps  = 2.2 hierarchies / second / bgp  
Memory: | ?  
Comments: | Light configuration (see below).   
  


BGP Options: | None  
---|---  
Duration: | 30 minutes  
Throughput: | 3,232 hierarchies / 30*60 = 1.7 hierarchies events / second   
Memory: | 800 MB per BGP  
Comments: | Heavy configuration (see below)  
  


BGP Options: | C8  
---|---  
Duration: | 10 minutes (including 3 minutes to initialise)  
Throughput: | 3,232 hierarchies / 7*60 / 8 bgps = 1.0 hierarchies events / second / bgp  
Memory: | ?  
Comments: | Heavy configuration (see below)  
  
Memory grows for each hierarchy with a different set of products.  This is due
to the retention of bgp evaluation orders for reuse in subsequent hierarchies.
Bill runs containing similar types of hierarchies allow greater reuse and
hence less memory growth.  Early investigations show 100 evaluation orders for
these 3000 hierarchies.   Other tests on hierarchies with 10,000 customers and
100,000 customers showed much greater reuse and a total memory growth to only
400 MB.

A heavier configuration resulted in an additional 18 calls to biSQLExecute
(trerwdb) and 15 calls to biSQLQuery (trerodb) per customer (at the customer
node context).  These calls resulted in additional 750ms / hierarchy.

Each evaluation order uses on average approx (800 MB / 100) = 8 MB.

* * *

Return to contents.

--------------------------------------------------
