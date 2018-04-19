"""

Author: Armon Dadgar
Start Date: April 16th, 2009
Description:
  Houses code which is common between the Linux, Darwin, and FreeBSD API's to avoid redundancy.

"""

import ctypes       # Allows us to make C calls
import ctypes.util  # Helps to find the C library

libc = ctypes.CDLL(ctypes.util.find_library("c"))

# Functions
_strerror = libc.strerror
_strerror.restype = ctypes.c_char_p

# This functions helps to conveniently retrieve the errno
# of the last call. This is a bit tedious to do, since 
# Python doesn't understand that this is a globally defined int
def get_ctypes_errno():
  errno_pointer = ctypes.cast(libc.errno, ctypes.POINTER(ctypes.c_int))
  err_val = errno_pointer.contents
  return err_val.value

# Returns the string version of the errno  
def get_ctypes_error_str():
  errornum = get_ctypes_errno()
  return _strerror(errornum)
