""" 
Author: Justin Cappos

Start Date: July 1st, 2008

Description:
Handles exiting and killing all threads, tracking CPU / Mem usage, etc.
"""

import threading
import os
import time

# needed for sys.stderr and windows Popen hackery
import sys

# needed for signal numbers
import signal

# needed for harshexit
import util.harshexit as harshexit

# print useful info when exiting...
import repy_exceptions.tracebackrepy as tracebackrepy

# used to query status, etc.
# This may fail on Windows CE
import subprocess

# need for status retrieval
# import util.statusstorage as statusstorage

# Get constants
import util.repy_constants as repy_constants

# This allows us to meter resource use
#import sandbox.nanny as nanny

# This is used for IPC
import marshal

# This will fail on non-windows systems
try:
  import windows_api as windows_api
except:
  windows_api = None

# Armon: This is a place holder for the module that will be imported later
os_api = None

# Armon: See additional imports at the bottom of the file

class UnsupportedSystemException(Exception):
  pass



###################     Publicly visible functions   #######################

# check the disk space used by a dir.
def compute_disk_use(dirname):
  # Convert path to absolute
  dirname = os.path.abspath(dirname)
  
  diskused = 0
  
  for filename in os.listdir(dirname):
    try:
      diskused = diskused + os.path.getsize(os.path.join(dirname, filename))
    except IOError:   # They likely deleted the file in the meantime...
      pass
    except OSError:   # They likely deleted the file in the meantime...
      pass

    # charge an extra 4K for each file to prevent lots of little files from 
    # using up the disk.   I'm doing this outside of the except clause in
    # the failure to get the size wasn't related to deletion
    diskused = diskused + 4096
        
  return diskused



# This will result in an internal thread on Windows
# and a thread on the external process for *NIX
def monitor_cpu_disk_and_mem():
  pass

# Elapsed time
elapsedtime = 0

# Store the uptime of the system when we first get loaded
starttime = 0
last_uptime = 0

# Timestamp from our starting point
last_timestamp = time.time()

# This is our uptime granularity
granularity = 1

# This ensures only one thread calling getruntime at any given time
runtimelock = threading.Lock()

def getruntime():
  """
   <Purpose>
      Return the amount of time the program has been running.   This is in
      wall clock time.   This function is not guaranteed to always return
      increasing values due to NTP, etc.

   <Arguments>
      None

   <Exceptions>
      None.

   <Side Effects>
      None

   <Remarks>
      By default this will have the same granularity as the system clock. However, if time 
      goes backward due to NTP or other issues, getruntime falls back to system uptime.
      This has much lower granularity, and varies by each system.

   <Returns>
      The elapsed time as float
  """
  global starttime, last_uptime, last_timestamp, elapsedtime, granularity, runtimelock
  
  # Get the lock
  runtimelock.acquire()
  
  # Check if Linux or BSD/Mac
  if ostype in ["Linux", "Darwin"]:
    uptime = os_api.get_system_uptime()

    # Check if time is going backward
    if uptime < last_uptime:
      # If the difference is less than 1 second, that is okay, since
      # The boot time is only precise to 1 second
      if (last_uptime - uptime) > 1:
        raise EnvironmentError("Uptime is going backwards!")
      else:
        # Use the last uptime
        uptime = last_uptime
        
        # No change in uptime
        diff_uptime = 0
    else:  
      # Current uptime, minus the last uptime
      diff_uptime = uptime - last_uptime
      
      # Update last uptime
      last_uptime = uptime

  # Check for windows  
  elif ostype in ["Windows"]:   
    # Release the lock
    runtimelock.release()
    
    # Time.clock returns elapsedtime since the first call to it, so this works for us
    return time.clock()
     
  # Who knows...  
  else:
    raise EnvironmentError("Unsupported Platform!")
  
  # Current uptime minus start time
  runtime = uptime - starttime
  
  # Get runtime from time.time
  current_time = time.time()
  
  # Current time, minus the last time
  diff_time = current_time - last_timestamp
  
  # Update the last_timestamp
  last_timestamp = current_time
  
  # Is time going backward?
  if diff_time < 0.0:
    # Add in the change in uptime
    elapsedtime += diff_uptime
  
  # Lets check if time.time is too skewed
  else:
    skew = abs(elapsedtime + diff_time - runtime)
    
    # If the skew is too great, use uptime instead of time.time()
    if skew < granularity:
      elapsedtime += diff_time
    else:
      elapsedtime += diff_uptime
  
  # Release the lock
  runtimelock.release()
          
  # Return the new elapsedtime
  return elapsedtime
 

# This lock is used to serialize calls to get_resources
get_resources_lock = threading.Lock()

# Cache the disk used from the external process
cached_disk_used = 0

# This array holds the times that repy was stopped.
# It is an array of tuples, of the form (time, amount)
# where time is when repy was stopped (from getruntime()) and amount
# is the stop time in seconds. The last process_stopped_max_entries are retained
process_stopped_timeline = []
process_stopped_max_entries = 100

# Method to expose resource limits and usage
def get_resources():
  """
  <Purpose>
    Returns the resource utilization limits as well
    as the current resource utilization.

  <Arguments>
    None.

  <Returns>
    A tuple of dictionaries and an array (limits, usage, stoptimes).

    Limits is the dictionary which maps the resource name
    to its maximum limit.

    Usage is the dictionary which maps the resource name
    to its current usage.

    Stoptimes is an array of tuples with the times which the Repy process
    was stopped and for how long, due to CPU over-use.
    Each entry in the array is a tuple (TOS, Sleep Time) where TOS is the
    time of stop (respective to getruntime()) and Sleep Time is how long the
    repy process was suspended.

    The stop times array holds a fixed number of the last stop times.
    Currently, it holds the last 100 stop times.
  """
  # Acquire the lock...
  get_resources_lock.acquire()

  # ...but always release it
  try:
    # Construct the dictionaries as copies from nanny
    (limits,usage) = 0, 0 #nanny.get_resource_information()


    # Calculate all the usage's
    pid = os.getpid()

    # Get CPU and memory, this is thread specific
    if ostype in ["Linux", "Darwin"]:
    
      # Get CPU first, then memory
      usage["cpu"] = os_api.get_process_cpu_time(pid)

      # This uses the cached PID data from the CPU check
      usage["memory"] = os_api.get_process_rss()

      # Get the thread specific CPU usage
      usage["threadcpu"] = os_api.get_current_thread_cpu_time() 


    # Windows Specific versions
    elif ostype in ["Windows"]:
    
      # Get the CPU time
      usage["cpu"] = windows_api.get_process_cpu_time(pid)

      # Get the memory, use the resident set size
      usage["memory"] = windows_api.process_memory_info(pid)['WorkingSetSize'] 

      # Get thread-level CPU 
      usage["threadcpu"] = windows_api.get_current_thread_cpu_time()

    # Unknown OS
    else:
      raise EnvironmentError("Unsupported Platform!")

    # Use the cached disk used amount
    usage["diskused"] = cached_disk_used

  finally:
    # Release the lock
    get_resources_lock.release()

  # Copy the stop times
  stoptimes = process_stopped_timeline[:]

  # Return the dictionaries and the stoptimes
  return (limits,usage,stoptimes)


###################     Windows specific functions   #######################

class WindowsNannyThread(threading.Thread):

  def __init__(self):
    threading.Thread.__init__(self,name="NannyThread")

  def run(self):
    # How often the memory will be checked (seconds)
    memory_check_interval = repy_constants.CPU_POLLING_FREQ_WIN
    # The ratio of the disk polling time to memory polling time.
    disk_to_memory_ratio = int(repy_constants.DISK_POLLING_HDD / memory_check_interval)
      
    # Which cycle number we're on  
    counter = 0
    
    # Elevate our priority, above normal is higher than the usercode, and is enough for disk/mem
    windows_api.set_current_thread_priority(windows_api.THREAD_PRIORITY_ABOVE_NORMAL)
    
    # need my pid to get a process handle...
    mypid = os.getpid()

    # run forever (only exit if an error occurs)
    while True:
      try:
        # Increment the interval counter
        counter += 1
        
        # Check memory use, get the WorkingSetSize or RSS
        memused = windows_api.process_memory_info(mypid)['WorkingSetSize']

        if memused > 10000000:#nanny.get_resource_limit("memory"):
          # We will be killed by the other thread...
          raise Exception("ayy")

        # Check if we should check the disk
        if (counter % disk_to_memory_ratio) == 0:
          # Check diskused
          diskused = compute_disk_use(repy_constants.REPY_CURRENT_DIR)
          if diskused > 1000000: #nanny.get_resource_limit("diskused"):
            raise Exception("ayylmao")
        # Sleep until the next iteration of checking the memory
        time.sleep(memory_check_interval)

        
      except windows_api.DeadProcess:
        #  Process may be dead, or die while checking memory use
        #  In any case, there is no reason to continue running, just exit
        harshexit.harshexit(99)

      except:
        tracebackrepy.handle_exception()
        print("Nanny died!   Trying to kill everything else")
        harshexit.harshexit(20)


# Windows specific CPU Nanny Stuff
winlastcpuinfo = [0,0]

# Enforces CPU limit on Windows and Windows CE
def win_check_cpu_use(cpulim, pid):
  global winlastcpuinfo
  
  # get use information and time...
  now = getruntime()

  # Get the total cpu time
  usertime = windows_api.get_process_cpu_time(pid)

  useinfo = [usertime, now]

  # get the previous time and cpu so we can compute the percentage
  oldusertime = winlastcpuinfo[0]
  oldnow = winlastcpuinfo[1]

  if winlastcpuinfo == [0,0]:
    winlastcpuinfo = useinfo
    # give them a free pass if it's their first time...
    return 0

  # save this data for next time...
  winlastcpuinfo = useinfo

  # Get the elapsed time...
  elapsedtime = now - oldnow

  # This is a problem
  if elapsedtime == 0:
    return -1 # Error condition
    
  # percent used is the amount of change divided by the time...
  percentused = (usertime - oldusertime) / elapsedtime

  # Calculate amount of time to sleep for
  stoptime = 0.02 #nanny.calculate_cpu_sleep_interval(cpulim, percentused,elapsedtime)

  if stoptime > 0.0:
    # Try to timeout the process
    if windows_api.timeout_process(pid, stoptime):
      # Log the stoptime
      process_stopped_timeline.append((now, stoptime))

      # Drop the first element if the length is greater than the maximum entries
      if len(process_stopped_timeline) > process_stopped_max_entries:
        process_stopped_timeline.pop(0)

      # Return how long we slept so parent knows whether it should sleep
      return stoptime
  
    else:
      # Process must have been making system call, try again next time
      return -1
  
  # If the stop time is 0, then avoid calling timeout_process
  else:
    return 0.0
    
            
# Dedicated Thread for monitoring CPU, this is run as a part of repy
class WinCPUNannyThread(threading.Thread):
  # Thread variables
  pid = 0 # Process pid
  
  def __init__(self):
    self.pid = os.getpid()
    threading.Thread.__init__(self,name="CPUNannyThread")    
      
  def run(self):
    # Elevate our priority, set us to the highest so that we can more effectively throttle
    success = windows_api.set_current_thread_priority(windows_api.THREAD_PRIORITY_HIGHEST)
    
    # If we failed to get HIGHEST priority, try above normal, else we're still at default
    if not success:
      windows_api.set_current_thread_priority(windows_api.THREAD_PRIORITY_ABOVE_NORMAL)
    
    # Run while the process is running
    while True:
      try:
        # Get the frequency
        frequency = repy_constants.CPU_POLLING_FREQ_WIN
        
        # Base amount of sleeping on return value of 
    	  # win_check_cpu_use to prevent under/over sleeping
        slept = win_check_cpu_use(nanny.get_resource_limit("cpu"), self.pid)
        
        if slept == -1:
          # Something went wrong, try again
          pass
        elif (slept < frequency):
          time.sleep(frequency-slept)

      except windows_api.DeadProcess:
        #  Process may be dead
        harshexit.harshexit(97)
        
      except:
        tracebackrepy.handle_exception()
        print("CPU Nanny died!   Trying to kill everything else")
        harshexit.harshexit(25)
              
              





##############     *nix specific functions (may include Mac)  ###############

# This method handles messages on the "diskused" channel from
# the external process. When the external process measures disk used,
# it is piped in and cached for calls to getresources.
def IPC_handle_diskused(bytes):
  cached_disk_used = bytes


# This method handles messages on the "repystopped" channel from
# the external process. When the external process stops repy, it sends
# a tuple with (TOS, amount) where TOS is time of stop (getruntime()) and
# amount is the amount of time execution was suspended.
def IPC_handle_stoptime(info):
  # Push this onto the timeline
  process_stopped_timeline.append(info)

  # Drop the first element if the length is greater than the max
  if len(process_stopped_timeline) > process_stopped_max_entries:
    process_stopped_timeline.pop(0)


# Use a special class of exception for when
# resource limits are exceeded
class ResourceException(Exception):
  pass


# Armon: Method to write a message to the pipe, used for IPC.
# This allows the pipe to be multiplexed by sending simple dictionaries
def write_message_to_pipe(writehandle, channel, data):
  """
  <Purpose>
    Writes a message to the pipe

  <Arguments>
    writehandle:
        A handle to a pipe which can be written to.

    channel:
        The channel used to describe the data. Used for multiplexing.

    data:
        The data to send.

  <Exceptions>
    As with os.write()
    EnvironmentError will be thrown if os.write() sends 0 bytes, indicating the
    pipe is broken.
  """
  # Construct the dictionary
  mesg_dict = {"ch":channel,"d":data}

  # Convert to a string
  mesg_dict_str = marshal.dumps(mesg_dict)

  # Make a full string
  mesg = str(len(mesg_dict_str)) + ":" + mesg_dict_str

  # Send this
  index = 0
  while index < len(mesg):
    bytes = os.write(writehandle, mesg[index:])
    if bytes == 0:
      raise EnvironmentError("Write send 0 bytes! Pipe broken!")
    index += bytes


# Armon: Method to read a message from the pipe, used for IPC.
# This allows the pipe to be multiplexed by sending simple dictionaries
def read_message_from_pipe(readhandle):
  """
  <Purpose>
    Reads a message from a pipe.

  <Arguments>
    readhandle:
        A handle to a pipe which can be read from

  <Exceptions>
    As with os.read().
    EnvironmentError will be thrown if os.read() returns a 0-length string, indicating
    the pipe is broken.

  <Returns>
    A tuple (Channel, Data) where Channel is used to multiplex the pipe.
  """
  # Read until we get to a colon
  data = ""
  index = 0

  # Loop until we get a message
  while True:

    # Read in data if the buffer is empty
    if index >= len(data):
      # Read 8 bytes at a time
      mesg = os.read(readhandle,8)
#     if len(mesg) == 0:
#       raise EnvironmentError("Read returned empty string! Pipe broken!")
      data += mesg

    # Increment the index while there is data and we have not found a colon
    while index < len(data) and data[index] != ":":
      index += 1

    # Check if we've found a colon
    if len(data) > index and data[index] == ":":
      # Get the message length
      mesg_length = int(data[:index])

      # Determine how much more data we need
      more_data = mesg_length - len(data) + index + 1

      # Read in the rest of the message
      while more_data > 0:
        mesg = os.read(readhandle, more_data)
#       if len(mesg) == 0:
#         raise EnvironmentError("Read returned empty string! Pipe broken!")
        data += mesg
        more_data -= len(mesg)

      # Done, convert the message to a dict
      whole_mesg = data[index+1:]
      mesg_dict = marshal.loads(whole_mesg)

      # Return a tuple (Channel, Data)
      return (mesg_dict["ch"],mesg_dict["d"])



# This dictionary defines the functions that handle messages
# on each channel. E.g. when a message arrives on the "repystopped" channel,
# the IPC_handle_stoptime function should be invoked to handle it.
IPC_HANDLER_FUNCTIONS = {"repystopped":IPC_handle_stoptime,
                         "diskused":IPC_handle_diskused }


# This thread checks that the parent process is alive and invokes
# delegate methods when messages arrive on the pipe.
class parent_process_checker(threading.Thread):
  def __init__(self, readhandle):
    """
    <Purpose>
      Terminates harshly if our parent dies before we do.

    <Arguments>
      readhandle: A file descriptor to the handle of a pipe to our parent.
    """
    # Name our self
    threading.Thread.__init__(self, name="ParentProcessChecker")

    # Store the handle
    self.readhandle = readhandle

  def run(self):
    # Run forever
    while True:
      # Read a message
      try:
        mesg = read_message_from_pipe(self.readhandle)
      except Exception as e:
        #print(e)
        break

      # Check for a handler function
      if mesg[0] in IPC_HANDLER_FUNCTIONS:
        # Invoke the handler function with the data
        handler = IPC_HANDLER_FUNCTIONS[mesg[0]]
        handler(mesg[1])

      # Print a message if there is a message on an unknown channel
      else:
        print("[WARN] Message on unknown channel from parent process:", mesg[0])



# For *NIX systems, there is an external process, and the 
# pid for the actual repy process is stored here
repy_process_id = None

 
###########     functions that help me figure out the os type    ###########

# Call init_ostype!!!
harshexit.init_ostype()

ostype = harshexit.ostype
osrealtype = harshexit.osrealtype

# Import the proper system wide API
if osrealtype == "Linux":
  import api.linux_api as os_api
elif osrealtype == "Darwin":
  import api.darwin_api as os_api
elif osrealtype == "FreeBSD":
  import api.freebsd_api as os_api
elif ostype == "Windows":
  # There is no real reason to do this, since windows is imported separately
  import api.windows_api as os_api
else:
  # This is a non-supported OS
  raise UnsupportedSystemException("The current Operating System is not supported! Fatal Error.")
  
# For Windows, we need to initialize time.clock()
if ostype in ["Windows"]:
  time.clock()

# Initialize getruntime for other platforms 
else:
  # Set the starttime to the initial uptime
  starttime = getruntime()
  last_uptime = starttime

  # Reset elapsed time 
  elapsedtime = 0
