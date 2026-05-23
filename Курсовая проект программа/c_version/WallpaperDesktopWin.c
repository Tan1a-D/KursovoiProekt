#include <windows.h>
#include <commdlg.h>
#include <shlobj.h>
#include <time.h>
#include <wchar.h>
#include <stdio.h>
#include <stdlib.h>

#define APP_TITLE L"Wallpaper Desktop"
#define APP_FOLDER L"WallpaperDesktop"
#define TIMER_ROTATE 1001

#define IDC_LIST 2001
#define IDC_ADD_FILES 2002
#define IDC_ADD_FOLDER 2003
#define IDC_REMOVE 2004
#define IDC_INTERVAL 2005
#define IDC_ORDER 2006
#define IDC_AUTOSTART 2007
#define IDC_CHANGE_NOW 2008
#define IDC_START_STOP 2009
#define IDC_HELP_BUTTON 2010
#define IDC_STATUS 2011

#define MAX_IMAGES 4096
#define MAX_PATH_LONG 4096

typedef struct AppState {
    HWND hwnd;
    HWND listbox;
    HWND intervalCombo;
    HWND orderCombo;
    HWND autostartCheck;
    HWND startStopButton;
    HWND statusLabel;
    HFONT font;
    wchar_t *images[MAX_IMAGES];
    int imageCount;
    int currentIndex;
    int intervalSeconds;
    int randomOrder;
    int running;
    __time64_t lastChanged;
    wchar_t appDir[MAX_PATH_LONG];
    wchar_t photosDir[MAX_PATH_LONG];
    wchar_t configPath[MAX_PATH_LONG];
    wchar_t imagesPath[MAX_PATH_LONG];
} AppState;

static AppState g_app;

static const wchar_t *intervalLabels[] = {
    L"1 минута",
    L"5 минут",
    L"30 минут",
    L"1 час",
    L"1 день"
};

static const int intervalValues[] = {
    60,
    5 * 60,
    30 * 60,
    60 * 60,
    24 * 60 * 60
};

static void SetStatus(const wchar_t *text) {
    if (g_app.statusLabel) {
        SetWindowTextW(g_app.statusLabel, text);
    }
}

static void JoinPath(wchar_t *out, size_t outSize, const wchar_t *left, const wchar_t *right) {
    swprintf(out, outSize, L"%ls\\%ls", left, right);
}

static const wchar_t *BaseName(const wchar_t *path) {
    const wchar_t *slash1 = wcsrchr(path, L'\\');
    const wchar_t *slash2 = wcsrchr(path, L'/');
    const wchar_t *slash = slash1 > slash2 ? slash1 : slash2;
    return slash ? slash + 1 : path;
}

static int EndsWithSupportedExtension(const wchar_t *path) {
    const wchar_t *dot = wcsrchr(path, L'.');
    if (!dot) {
        return 0;
    }
    return _wcsicmp(dot, L".jpg") == 0 ||
           _wcsicmp(dot, L".jpeg") == 0 ||
           _wcsicmp(dot, L".png") == 0 ||
           _wcsicmp(dot, L".bmp") == 0 ||
           _wcsicmp(dot, L".gif") == 0 ||
           _wcsicmp(dot, L".webp") == 0;
}

static void FreeImages(void) {
    for (int i = 0; i < g_app.imageCount; i++) {
        free(g_app.images[i]);
        g_app.images[i] = NULL;
    }
    g_app.imageCount = 0;
    g_app.currentIndex = -1;
}

static int AddImagePath(const wchar_t *path) {
    if (g_app.imageCount >= MAX_IMAGES) {
        return 0;
    }
    for (int i = 0; i < g_app.imageCount; i++) {
        if (_wcsicmp(g_app.images[i], path) == 0) {
            return 0;
        }
    }
    size_t len = wcslen(path);
    wchar_t *copy = (wchar_t *)calloc(len + 1, sizeof(wchar_t));
    if (!copy) {
        return 0;
    }
    wcscpy(copy, path);
    g_app.images[g_app.imageCount++] = copy;
    return 1;
}

static void RefreshListbox(void) {
    if (!g_app.listbox) {
        return;
    }
    SendMessageW(g_app.listbox, LB_RESETCONTENT, 0, 0);
    for (int i = 0; i < g_app.imageCount; i++) {
        SendMessageW(g_app.listbox, LB_ADDSTRING, 0, (LPARAM)BaseName(g_app.images[i]));
    }
}

static void EnsureAppFolders(void) {
    wchar_t roaming[MAX_PATH_LONG];
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_APPDATA | CSIDL_FLAG_CREATE, NULL, SHGFP_TYPE_CURRENT, roaming))) {
        wcscpy(roaming, L".");
    }
    JoinPath(g_app.appDir, MAX_PATH_LONG, roaming, APP_FOLDER);
    JoinPath(g_app.photosDir, MAX_PATH_LONG, g_app.appDir, L"photos");
    JoinPath(g_app.configPath, MAX_PATH_LONG, g_app.appDir, L"config.ini");
    JoinPath(g_app.imagesPath, MAX_PATH_LONG, g_app.appDir, L"images.txt");
    CreateDirectoryW(g_app.appDir, NULL);
    CreateDirectoryW(g_app.photosDir, NULL);
}

static void SaveImageList(void) {
    FILE *file = _wfopen(g_app.imagesPath, L"wb");
    if (!file) {
        return;
    }
    wchar_t bom = 0xFEFF;
    fwrite(&bom, sizeof(wchar_t), 1, file);
    for (int i = 0; i < g_app.imageCount; i++) {
        fwrite(g_app.images[i], sizeof(wchar_t), wcslen(g_app.images[i]), file);
        wchar_t newline = L'\n';
        fwrite(&newline, sizeof(wchar_t), 1, file);
    }
    fclose(file);
}

static void LoadImageList(void) {
    FILE *file = _wfopen(g_app.imagesPath, L"rb");
    if (!file) {
        return;
    }
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    if (size <= 0) {
        fclose(file);
        return;
    }

    wchar_t *buffer = (wchar_t *)calloc((size / sizeof(wchar_t)) + 2, sizeof(wchar_t));
    if (!buffer) {
        fclose(file);
        return;
    }
    size_t count = fread(buffer, sizeof(wchar_t), size / sizeof(wchar_t), file);
    fclose(file);
    buffer[count] = L'\0';

    wchar_t *cursor = buffer;
    if (*cursor == 0xFEFF) {
        cursor++;
    }
    wchar_t *line = cursor;
    while (*cursor) {
        if (*cursor == L'\r' || *cursor == L'\n') {
            *cursor = L'\0';
            if (*line && GetFileAttributesW(line) != INVALID_FILE_ATTRIBUTES) {
                AddImagePath(line);
            }
            cursor++;
            while (*cursor == L'\r' || *cursor == L'\n') {
                cursor++;
            }
            line = cursor;
        } else {
            cursor++;
        }
    }
    if (*line && GetFileAttributesW(line) != INVALID_FILE_ATTRIBUTES) {
        AddImagePath(line);
    }
    free(buffer);
}

static void SaveConfig(void) {
    wchar_t value[64];
    swprintf(value, 64, L"%d", g_app.intervalSeconds);
    WritePrivateProfileStringW(L"settings", L"interval", value, g_app.configPath);
    swprintf(value, 64, L"%d", g_app.randomOrder);
    WritePrivateProfileStringW(L"settings", L"randomOrder", value, g_app.configPath);
    swprintf(value, 64, L"%d", g_app.currentIndex);
    WritePrivateProfileStringW(L"settings", L"currentIndex", value, g_app.configPath);
    swprintf(value, 64, L"%lld", (long long)g_app.lastChanged);
    WritePrivateProfileStringW(L"settings", L"lastChanged", value, g_app.configPath);
    SaveImageList();
}

static void LoadConfig(void) {
    EnsureAppFolders();
    g_app.intervalSeconds = GetPrivateProfileIntW(L"settings", L"interval", 24 * 60 * 60, g_app.configPath);
    g_app.randomOrder = GetPrivateProfileIntW(L"settings", L"randomOrder", 0, g_app.configPath);
    g_app.currentIndex = GetPrivateProfileIntW(L"settings", L"currentIndex", -1, g_app.configPath);
    wchar_t lastChanged[64];
    GetPrivateProfileStringW(L"settings", L"lastChanged", L"0", lastChanged, 64, g_app.configPath);
    g_app.lastChanged = _wtoi64(lastChanged);
    LoadImageList();
    if (g_app.currentIndex >= g_app.imageCount) {
        g_app.currentIndex = g_app.imageCount - 1;
    }
}

static void BuildUniqueDestination(const wchar_t *source, wchar_t *dest, size_t destSize) {
    const wchar_t *name = BaseName(source);
    JoinPath(dest, destSize, g_app.photosDir, name);
    if (GetFileAttributesW(dest) == INVALID_FILE_ATTRIBUTES) {
        return;
    }

    wchar_t stem[MAX_PATH_LONG];
    wchar_t ext[64];
    wcscpy(stem, name);
    wchar_t *dot = wcsrchr(stem, L'.');
    if (dot) {
        wcsncpy(ext, dot, 63);
        ext[63] = L'\0';
        *dot = L'\0';
    } else {
        ext[0] = L'\0';
    }

    for (int i = 1; i < 10000; i++) {
        swprintf(dest, destSize, L"%ls\\%ls_%d%ls", g_app.photosDir, stem, i, ext);
        if (GetFileAttributesW(dest) == INVALID_FILE_ATTRIBUTES) {
            return;
        }
    }
}

static int ImportOneImage(const wchar_t *source) {
    if (!EndsWithSupportedExtension(source)) {
        return 0;
    }
    if (GetFileAttributesW(source) == INVALID_FILE_ATTRIBUTES) {
        return 0;
    }
    wchar_t dest[MAX_PATH_LONG];
    BuildUniqueDestination(source, dest, MAX_PATH_LONG);
    if (!CopyFileW(source, dest, TRUE)) {
        return 0;
    }
    return AddImagePath(dest);
}

static void SelectFiles(void) {
    wchar_t buffer[65536];
    ZeroMemory(buffer, sizeof(buffer));

    OPENFILENAMEW ofn;
    ZeroMemory(&ofn, sizeof(ofn));
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = g_app.hwnd;
    ofn.lpstrFilter = L"Изображения\0*.jpg;*.jpeg;*.png;*.bmp;*.gif;*.webp\0Все файлы\0*.*\0";
    ofn.lpstrFile = buffer;
    ofn.nMaxFile = 65536;
    ofn.Flags = OFN_ALLOWMULTISELECT | OFN_EXPLORER | OFN_FILEMUSTEXIST;

    if (!GetOpenFileNameW(&ofn)) {
        return;
    }

    int added = 0;
    wchar_t *cursor = buffer;
    wchar_t directory[MAX_PATH_LONG];
    wcscpy(directory, cursor);
    cursor += wcslen(cursor) + 1;

    if (*cursor == L'\0') {
        added += ImportOneImage(directory);
    } else {
        while (*cursor) {
            wchar_t fullPath[MAX_PATH_LONG];
            JoinPath(fullPath, MAX_PATH_LONG, directory, cursor);
            added += ImportOneImage(fullPath);
            cursor += wcslen(cursor) + 1;
        }
    }

    SaveConfig();
    RefreshListbox();
    wchar_t status[128];
    swprintf(status, 128, L"Добавлено изображений: %d", added);
    SetStatus(status);
}

static void ScanFolderRecursive(const wchar_t *folder, int *added) {
    wchar_t search[MAX_PATH_LONG];
    swprintf(search, MAX_PATH_LONG, L"%ls\\*", folder);

    WIN32_FIND_DATAW data;
    HANDLE handle = FindFirstFileW(search, &data);
    if (handle == INVALID_HANDLE_VALUE) {
        return;
    }

    do {
        if (wcscmp(data.cFileName, L".") == 0 || wcscmp(data.cFileName, L"..") == 0) {
            continue;
        }
        wchar_t fullPath[MAX_PATH_LONG];
        JoinPath(fullPath, MAX_PATH_LONG, folder, data.cFileName);
        if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            ScanFolderRecursive(fullPath, added);
        } else {
            *added += ImportOneImage(fullPath);
        }
    } while (FindNextFileW(handle, &data));

    FindClose(handle);
}

static void SelectFolder(void) {
    BROWSEINFOW bi;
    ZeroMemory(&bi, sizeof(bi));
    bi.hwndOwner = g_app.hwnd;
    bi.lpszTitle = L"Выберите папку с фотографиями";
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;

    LPITEMIDLIST pidl = SHBrowseForFolderW(&bi);
    if (!pidl) {
        return;
    }

    wchar_t folder[MAX_PATH_LONG];
    if (SHGetPathFromIDListW(pidl, folder)) {
        int added = 0;
        ScanFolderRecursive(folder, &added);
        SaveConfig();
        RefreshListbox();
        wchar_t status[128];
        swprintf(status, 128, L"Добавлено изображений: %d", added);
        SetStatus(status);
    }
    CoTaskMemFree(pidl);
}

static int SetWallpaper(const wchar_t *path) {
    return SystemParametersInfoW(
        SPI_SETDESKWALLPAPER,
        0,
        (PVOID)path,
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    );
}

static int ChooseNextIndex(void) {
    if (g_app.imageCount <= 0) {
        return -1;
    }
    if (g_app.randomOrder) {
        if (g_app.imageCount == 1) {
            return 0;
        }
        int next = g_app.currentIndex;
        while (next == g_app.currentIndex) {
            next = rand() % g_app.imageCount;
        }
        return next;
    }
    return (g_app.currentIndex + 1) % g_app.imageCount;
}

static int ChangeNow(void) {
    if (g_app.imageCount == 0) {
        MessageBoxW(g_app.hwnd, L"Добавьте хотя бы одну фотографию.", APP_TITLE, MB_ICONWARNING);
        return 0;
    }
    int index = ChooseNextIndex();
    if (index < 0) {
        return 0;
    }
    if (!SetWallpaper(g_app.images[index])) {
        MessageBoxW(g_app.hwnd, L"Не удалось сменить обои рабочего стола.", APP_TITLE, MB_ICONERROR);
        return 0;
    }
    g_app.currentIndex = index;
    g_app.lastChanged = _time64(NULL);
    SaveConfig();
    wchar_t status[MAX_PATH_LONG + 64];
    swprintf(status, MAX_PATH_LONG + 64, L"Установлено: %ls", BaseName(g_app.images[index]));
    SetStatus(status);
    return 1;
}

static void RemoveSelected(void) {
    int selected = (int)SendMessageW(g_app.listbox, LB_GETCURSEL, 0, 0);
    if (selected == LB_ERR || selected < 0 || selected >= g_app.imageCount) {
        return;
    }
    free(g_app.images[selected]);
    for (int i = selected; i < g_app.imageCount - 1; i++) {
        g_app.images[i] = g_app.images[i + 1];
    }
    g_app.imageCount--;
    if (g_app.currentIndex >= g_app.imageCount) {
        g_app.currentIndex = g_app.imageCount - 1;
    }
    SaveConfig();
    RefreshListbox();
    SetStatus(L"Изображение удалено из списка");
}

static void ReadControls(void) {
    int intervalIndex = (int)SendMessageW(g_app.intervalCombo, CB_GETCURSEL, 0, 0);
    if (intervalIndex < 0 || intervalIndex >= 5) {
        intervalIndex = 4;
    }
    g_app.intervalSeconds = intervalValues[intervalIndex];

    int orderIndex = (int)SendMessageW(g_app.orderCombo, CB_GETCURSEL, 0, 0);
    g_app.randomOrder = orderIndex == 1;
}

static void SelectCurrentSettings(void) {
    int intervalIndex = 4;
    for (int i = 0; i < 5; i++) {
        if (intervalValues[i] == g_app.intervalSeconds) {
            intervalIndex = i;
            break;
        }
    }
    SendMessageW(g_app.intervalCombo, CB_SETCURSEL, intervalIndex, 0);
    SendMessageW(g_app.orderCombo, CB_SETCURSEL, g_app.randomOrder ? 1 : 0, 0);
}

static int IsAutostartEnabled(void) {
    HKEY key;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, KEY_READ, &key) != 
ERROR_SUCCESS) {
        return 0;
    }
    wchar_t value[MAX_PATH_LONG];
    DWORD size = sizeof(value);
    LONG result = RegQueryValueExW(key, APP_TITLE, NULL, NULL, (LPBYTE)value, &size);
    RegCloseKey(key);
    return result == ERROR_SUCCESS;
}

static void SetAutostart(int enabled) {
    HKEY key;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, KEY_SET_VALUE, &key)
 != ERROR_SUCCESS) {
        return;
    }
    if (enabled) {
        wchar_t exePath[MAX_PATH_LONG];
        wchar_t command[MAX_PATH_LONG + 32];
        GetModuleFileNameW(NULL, exePath, MAX_PATH_LONG);
        swprintf(command, MAX_PATH_LONG + 32, L"\"%ls\" --daemon", exePath);
        RegSetValueExW(key, APP_TITLE, 0, REG_SZ, (const BYTE *)command, (DWORD)((wcslen(command) + 1) * 
sizeof(wchar_t)));
    } else {
        RegDeleteValueW(key, APP_TITLE);
    }
    RegCloseKey(key);
}

static void ToggleRunning(void) {
    ReadControls();
    SaveConfig();
    if (g_app.running) {
        KillTimer(g_app.hwnd, TIMER_ROTATE);
        g_app.running = 0;
        SetWindowTextW(g_app.startStopButton, L"Старт");
        SetStatus(L"Автоматическая смена остановлена");
        return;
    }

    if (!ChangeNow()) {
        return;
    }
    UINT delay = (UINT)g_app.intervalSeconds * 1000U;
    SetTimer(g_app.hwnd, TIMER_ROTATE, delay, NULL);
    g_app.running = 1;
    SetWindowTextW(g_app.startStopButton, L"Стоп");
    SetStatus(L"Автоматическая смена включена");
}

static void ShowHelp(void) {
    MessageBoxW(
        g_app.hwnd,
        L"1. Нажмите «Добавить фото» или «Добавить папку».\n"
        L"2. Выберите интервал смены обоев.\n"
        L"3. Нажмите «Сменить сейчас» для ручной смены.\n"
        L"4. Нажмите «Старт» для автоматической смены.\n"
        L"5. Флажок автозапуска включает фоновый режим при входе в Windows.",
        L"Справка",
        MB_OK | MB_ICONINFORMATION
    );
}

static void ApplyFont(HWND hwnd) {
    SendMessageW(hwnd, WM_SETFONT, (WPARAM)g_app.font, TRUE);
}

static HWND AddControl(const wchar_t *className, const wchar_t *text, DWORD style, int x, int y, int w, int h, int id)
 {
    HWND control = CreateWindowExW(
        0,
        className,
        text,
        WS_CHILD | WS_VISIBLE | style,
        x,
        y,
        w,
        h,
        g_app.hwnd,
        (HMENU)(INT_PTR)id,
        GetModuleHandleW(NULL),
        NULL
    );
    ApplyFont(control);
    return control;
}

static void BuildInterface(HWND hwnd) {
    g_app.hwnd = hwnd;
    g_app.font = CreateFontW(
        -16, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI"
    );

    AddControl(L"STATIC", L"Фотографии", 0, 16, 14, 160, 24, 0);
    g_app.listbox = AddControl(
        L"LISTBOX",
        L"",
        WS_BORDER | LBS_NOTIFY | WS_VSCROLL,
        16,
        42,
        430,
        292,
        IDC_LIST
    );

    AddControl(L"BUTTON", L"Добавить фото", 0, 16, 346, 132, 34, IDC_ADD_FILES);
    AddControl(L"BUTTON", L"Добавить папку", 0, 158, 346, 132, 34, IDC_ADD_FOLDER);
    AddControl(L"BUTTON", L"Удалить", 0, 300, 346, 146, 34, IDC_REMOVE);

    AddControl(L"STATIC", L"Интервал", 0, 474, 44, 110, 24, 0);
    g_app.intervalCombo = AddControl(L"COMBOBOX", L"", CBS_DROPDOWNLIST, 584, 40, 190, 140, IDC_INTERVAL);
    for (int i = 0; i < 5; i++) {
        SendMessageW(g_app.intervalCombo, CB_ADDSTRING, 0, (LPARAM)intervalLabels[i]);
    }

    AddControl(L"STATIC", L"Порядок", 0, 474, 88, 110, 24, 0);
    g_app.orderCombo = AddControl(L"COMBOBOX", L"", CBS_DROPDOWNLIST, 584, 84, 190, 100, IDC_ORDER);
    SendMessageW(g_app.orderCombo, CB_ADDSTRING, 0, (LPARAM)L"По порядку");
    SendMessageW(g_app.orderCombo, CB_ADDSTRING, 0, (LPARAM)L"Случайно");
    SelectCurrentSettings();

    g_app.autostartCheck = AddControl(L"BUTTON", L"Запускать вместе с Windows", BS_AUTOCHECKBOX, 474, 132, 300, 28, 
IDC_AUTOSTART);
    SendMessageW(g_app.autostartCheck, BM_SETCHECK, IsAutostartEnabled() ? BST_CHECKED : BST_UNCHECKED, 0);

    AddControl(L"BUTTON", L"Сменить сейчас", 0, 474, 184, 145, 38, IDC_CHANGE_NOW);
    g_app.startStopButton = AddControl(L"BUTTON", L"Старт", 0, 629, 184, 145, 38, IDC_START_STOP);
    AddControl(L"BUTTON", L"Справка", 0, 474, 236, 300, 34, IDC_HELP_BUTTON);

    g_app.statusLabel = AddControl(L"STATIC", L"Готово", WS_BORDER, 16, 400, 758, 28, IDC_STATUS);
    RefreshListbox();
}

static LRESULT CALLBACK WindowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
        case WM_CREATE:
            BuildInterface(hwnd);
            return 0;

        case WM_COMMAND:
            switch (LOWORD(wParam)) {
                case IDC_ADD_FILES:
                    SelectFiles();
                    return 0;
                case IDC_ADD_FOLDER:
                    SelectFolder();
                    return 0;
                case IDC_REMOVE:
                    RemoveSelected();
                    return 0;
                case IDC_INTERVAL:
                case IDC_ORDER:
                    if (HIWORD(wParam) == CBN_SELCHANGE) {
                        ReadControls();
                        SaveConfig();
                    }
                    return 0;
                case IDC_AUTOSTART:
                    SetAutostart(SendMessageW(g_app.autostartCheck, BM_GETCHECK, 0, 0) == BST_CHECKED);
                    SetStatus(L"Настройка автозапуска сохранена");
                    return 0;
                case IDC_CHANGE_NOW:
                    ReadControls();
                    SaveConfig();
                    ChangeNow();
                    return 0;
                case IDC_START_STOP:
                    ToggleRunning();
                    return 0;
                case IDC_HELP_BUTTON:
                    ShowHelp();
                    return 0;
                default:
                    break;
            }
            return 0;

        case WM_TIMER:
            if (wParam == TIMER_ROTATE) {
                ChangeNow();
                return 0;
            }
            break;

        case WM_DESTROY:
            if (g_app.running) {
                KillTimer(hwnd, TIMER_ROTATE);
            }
            SaveConfig();
            FreeImages();
            if (g_app.font) {
                DeleteObject(g_app.font);
            }
            PostQuitMessage(0);
            return 0;

        default:
            break;
    }
    return DefWindowProcW(hwnd, message, wParam, lParam);
}

static int IsDue(void) {
    if (g_app.lastChanged <= 0) {
        return 1;
    }
    return (_time64(NULL) - g_app.lastChanged) >= g_app.intervalSeconds;
}

static void RunDaemon(void) {
    LoadConfig();
    srand((unsigned int)GetTickCount());
    for (;;) {
        if (g_app.imageCount > 0 && IsDue()) {
            int index = ChooseNextIndex();
            if (index >= 0 && SetWallpaper(g_app.images[index])) {
                g_app.currentIndex = index;
                g_app.lastChanged = _time64(NULL);
                SaveConfig();
            }
        }
        int sleepMs = (g_app.intervalSeconds / 4) * 1000;
        if (sleepMs < 10000) {
            sleepMs = 10000;
        }
        if (sleepMs > 60000) {
            sleepMs = 60000;
        }
        Sleep((DWORD)sleepMs);
    }
}

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, PWSTR pCmdLine, int nCmdShow) {
    (void)hPrevInstance;
    CoInitialize(NULL);
    LoadConfig();
    srand((unsigned int)GetTickCount());

    if (wcsstr(pCmdLine, L"--daemon") != NULL) {
        RunDaemon();
        return 0;
    }

    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = L"WallpaperDesktopWindow";
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);

    RegisterClassW(&wc);

    HWND hwnd = CreateWindowExW(
        0,
        wc.lpszClassName,
        APP_TITLE,
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        810,
        480,
        NULL,
        NULL,
        hInstance,
        NULL
    );

    if (!hwnd) {
        CoUninitialize();
        return 1;
    }

    ShowWindow(hwnd, nCmdShow);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    CoUninitialize();
    return 0;
}