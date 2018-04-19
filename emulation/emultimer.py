"""
   Author: Justin Cappos

   Start Date: 29 June 2008

   Description:

   Timer functions for the sandbox.   This does sleep as well as setting and
   cancelling timers.
"""

import threading

try:
  import thread
except ImportError:
  import _thread # Armon: this is to catch thread.error

# for printing exceptions
import repy_exceptions.tracebackrepy as tracebackrepy

# for harshexit
import util.harshexit as harshexit

# For getruntime()
import sandbox.nonportable as nonportable

# For sleep
import time

# Import the exception hierarchy
from repy_exceptions import *

##### Constants

# Armon: Prefix for use with event handles
EVENT_PREFIX = "_EVENT:"

# Store callable
safe_callable = callable


##### Public Functions

def sleep(seconds):
  """
   <Purpose>
      Allow the current event to pause execution (similar to time.sleep()).
      This function will not return early for any reason

   <Arguments>
      seconds:
         The number of seconds to sleep.   This can be a floating point value

   <Exceptions>
      RepyArgumentException if seconds is not an int/long/float.

   <Side Effects>
      None.

   <Returns>
      None.
  """

  # Check seconds to ensure it is a valid type.
  if type(seconds) not in [int, float, int]:
    raise RepyArgumentError("Invalid type " + str(type(seconds)))

  # Using getruntime() in lieu of time.time() because we want elapsed time 
  # regardless of the oddities of NTP
  start = nonportable.getruntime()
  sleeptime = seconds

  # Return no earlier than the finish time
  finish = start + seconds

  while sleeptime > 0.0:
    time.sleep(sleeptime)

    # If sleeptime > 0.0 then I woke up early...
    sleeptime = finish - nonportable.getruntime()
