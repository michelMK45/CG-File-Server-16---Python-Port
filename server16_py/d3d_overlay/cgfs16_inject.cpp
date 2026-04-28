/**
 * cgfs16_inject.cpp  -  x86 DLL injector helper for CGFS16
 *
 * Compiled as x86 so it can inject into 32-bit FIFA 16.
 * Usage: cgfs16_inject.exe <pid> <absolute_dll_path>
 * Exit codes: 0=ok, 2=OpenProcess, 3=VirtualAllocEx, 4=WriteProcessMemory,
 *             5=CreateRemoteThread, 6=Timeout, 7=LoadLibraryW NULL, 10=64-bit target
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "kernel32.lib")

/* Convert wchar_t* to narrow char* using ANSI codepage */
static char g_dllNarrow[2048];
static char g_errBuf[256];

int wmain(int argc, wchar_t* argv[])
{
    if (argc < 3) {
        fprintf(stderr, "Usage: cgfs16_inject.exe <pid> <dll_path>\n");
        return 1;
    }

    DWORD          pid = (DWORD)wcstoul(argv[1], NULL, 10);
    const wchar_t* dll = argv[2];

    /* Convert DLL path to narrow for diagnostic output */
    WideCharToMultiByte(CP_ACP, 0, dll, -1, g_dllNarrow, sizeof(g_dllNarrow)-1, NULL, NULL);

    DWORD access =
        PROCESS_CREATE_THREAD  |
        PROCESS_VM_OPERATION   |
        PROCESS_VM_WRITE       |
        PROCESS_VM_READ        |
        PROCESS_QUERY_INFORMATION;

    HANDLE hProc = OpenProcess(access, FALSE, pid);
    if (!hProc) {
        fprintf(stderr, "OpenProcess(%lu) failed: %lu\n", pid, GetLastError());
        return 2;
    }

    /* Detect bitness mismatch: we are x86; if target is NOT WOW64 on a 64-bit OS,
       the target is a native 64-bit process and we cannot inject into it. */
    BOOL weAre64   = FALSE;
    BOOL targetIs32 = FALSE;
    IsWow64Process(GetCurrentProcess(), &weAre64);
    IsWow64Process(hProc, &targetIs32);

    fprintf(stdout, "DEBUG: we_are_wow64=%d target_is_wow64=%d\n",
            (int)weAre64, (int)targetIs32);

    if (weAre64 && !targetIs32) {
        fprintf(stderr, "ERROR: target pid=%lu is a native 64-bit process; "
                "cannot inject x86 DLL\n", pid);
        CloseHandle(hProc);
        return 10;
    }

    /* Allocate remote memory for the DLL path */
    SIZE_T pathBytes = (wcslen(dll) + 1) * sizeof(wchar_t);
    LPVOID remPath   = VirtualAllocEx(hProc, NULL, pathBytes,
                                      MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remPath) {
        fprintf(stderr, "VirtualAllocEx failed: %lu\n", GetLastError());
        CloseHandle(hProc);
        return 3;
    }

    if (!WriteProcessMemory(hProc, remPath, dll, pathBytes, NULL)) {
        fprintf(stderr, "WriteProcessMemory failed: %lu\n", GetLastError());
        VirtualFreeEx(hProc, remPath, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return 4;
    }

    /* LoadLibraryW address - same in all x86 processes on the same OS */
    HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
    LPTHREAD_START_ROUTINE loadLib =
        (LPTHREAD_START_ROUTINE)GetProcAddress(hKernel32, "LoadLibraryW");

    if (!loadLib) {
        fprintf(stderr, "GetProcAddress(LoadLibraryW) failed: %lu\n", GetLastError());
        VirtualFreeEx(hProc, remPath, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return 8;
    }

    fprintf(stdout, "DEBUG: Calling CreateRemoteThread with LoadLibraryW=0x%p dll=%s\n",
            (void*)loadLib, g_dllNarrow);

    HANDLE hThread = CreateRemoteThread(
        hProc, NULL, 0, loadLib, remPath, 0, NULL);
    if (!hThread) {
        fprintf(stderr, "CreateRemoteThread failed: %lu\n", GetLastError());
        VirtualFreeEx(hProc, remPath, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return 5;
    }

    DWORD waitResult = WaitForSingleObject(hThread, 8000);
    DWORD exitCode   = 0;
    GetExitCodeThread(hThread, &exitCode);
    CloseHandle(hThread);

    VirtualFreeEx(hProc, remPath, 0, MEM_RELEASE);
    CloseHandle(hProc);

    if (waitResult == WAIT_TIMEOUT) {
        fprintf(stderr, "Timeout waiting for LoadLibraryW\n");
        return 6;
    }
    if (exitCode == 0) {
        fprintf(stderr, "LoadLibraryW returned NULL in target (DLL rejected or path wrong)\n");
        return 7;
    }

    fprintf(stdout, "OK pid=%lu hmod=0x%08lX\n", pid, exitCode);
    return 0;
}
