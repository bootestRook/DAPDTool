"""One application per Windows user, released by the kernel on process exit."""
import win32api
import win32con
import win32event
import win32security
import winerror


def acquire_instance_lock():
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        user = win32security.ConvertSidToStringSid(sid)
    finally:
        token.Close()
    handle = win32event.CreateMutex(None, False, "Local\\DAPDTaskTool." + user)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        handle.Close()
        return None
    return handle
