# -*- coding: utf-8 -*-

# =========================================================================================
#
#   ConnectionBreaker
#
#   A slick utility to selectively sever network connections for any running process.
#   Perfect for gamers, developers, or anyone needing to firewall an app on the fly.
#
#   Crafted with Python and PyQt6.
#
# =========================================================================================


import sys
import os
import subprocess
import psutil
import keyboard
import cv2
import threading
import ctypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QPushButton, QLabel, QDialog, QListWidget, QHBoxLayout,
                             QSystemTrayIcon, QMenu, QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSharedMemory
from PyQt6.QtGui import QIcon, QAction, QImage, QPainter, QBrush, QColor
from PyQt6 import QtCore, QtWidgets
import pygetwindow as gw

def is_admin():
    """ Checks if the script is running with administrator privileges. """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# --- Globals & Constants ---
# Yo, trying to keep the chaos organized. These are our app-wide constants.

# We need to know where our assets are, especially when the app is bundled by PyInstaller.
# This little helper function figures out the correct path whether we're running from source
# or as a standalone executable. It's a classic trick of the trade.
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # We also need to add the 'assets' folder to the path.
        base_path = os.path.join(sys._MEIPASS, 'assets')
    except Exception:
        # Not bundled, running from source. Go up from 'src' to parent, then 'assets'
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets'))
    return os.path.join(base_path, relative_path)

# Paths to our asset files. Keep 'em handy.
ICON_PATH = resource_path("icon.ico")
BG_VIDEO_PATH = resource_path("background.mp4")
CPORTS_PATH = resource_path("cports.exe")

# This is a godsend for hotkeys. Users might type in Cyrillic, but the 'keyboard'
# library only speaks English. This map translates RU keystrokes to their EN layout counterparts.
RU_TO_EN_MAP = {
    'й': 'q', 'ц': 'w', 'у': 'e', 'к': 'r', 'е': 't', 'н': 'y', 'г': 'u', 'ш': 'i', 'щ': 'o', 'з': 'p', 'х': '[', 'ъ': ']',
    'ф': 'a', 'ы': 's', 'в': 'd', 'а': 'f', 'п': 'g', 'р': 'h', 'о': 'j', 'л': 'k', 'д': 'l', 'ж': ';', 'э': "'",
    'я': 'z', 'ч': 'x', 'с': 'c', 'м': 'v', 'и': 'b', 'т': 'n', 'ь': 'm', 'б': ',', 'ю': '.',
}

# --- Utility Classes & Threads ---

def is_valid_hotkey(hotkey_str):
    """
    Checks if a hotkey string is a valid combination.
    A valid combo is 1+ modifiers (ctrl, alt, shift) and ONE other key.
    e.g., 'ctrl+alt+k' is good, 'a+b' is bad.
    """
    if not hotkey_str:
        return False
    
    MODIFIERS = {'ctrl', 'alt', 'shift', 'win'}
    parts = {part.strip().lower() for part in hotkey_str.split('+')}
    
    non_modifier_keys = [p for p in parts if p not in MODIFIERS]
    
    # A valid hotkey has exactly one non-modifier key.
    return len(non_modifier_keys) == 1


class VideoThread(QThread):
    """
    This bad boy runs our background video in a separate thread.
    Why? Because rendering video is heavy stuff. If we did this on the main GUI thread,
    the whole app would stutter and freeze. Nobody wants that.
    It continuously grabs frames, converts 'em to a QImage, and shoots 'em over
    to the main thread via a signal.
    """
    frame_ready = pyqtSignal(QImage)

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._is_running = True

    def run(self):
        if not os.path.exists(self.video_path):
            print(f"Dude, where's my video? Not found at {self.video_path}")
            return
        
        video_capture = cv2.VideoCapture(self.video_path)
        fps = video_capture.get(cv2.CAP_PROP_FPS)
        delay = int(1000 / fps) if fps > 0 else 33 # 33ms is ~30fps, a safe fallback.

        while self._is_running:
            ret, frame = video_capture.read()
            if ret:
                # OpenCV gives us BGR, but Qt wants RGB. Gotta swap 'em.
                height, width, channel = frame.shape
                bytes_per_line = 3 * width
                q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_BGR888).rgbSwapped()
                self.frame_ready.emit(q_image)
                self.msleep(delay)
            else:
                # Loop it! If the video ends, just start it over.
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        video_capture.release()

    def stop(self):
        """ Kills the thread gracefully. """
        self._is_running = False
        self.wait()


class HotkeyListener(QThread):
    """
    Listens for the global hotkey in a separate thread.
    Just like the video, this needs to be off the main thread to prevent blocking the GUI.
    When the hotkey is pressed, it fires a signal. Simple and effective.
    """
    hotkey_pressed = pyqtSignal()

    def __init__(self, hotkey, parent=None):
        super().__init__(parent)
        self.hotkey = hotkey
        self._is_running = True

    def run(self):
        # We wrap this in a try/finally to make sure the hotkey gets unregistered.
        # Otherwise, you'd have a zombie hotkey listener even after the app closes.
        try:
            keyboard.add_hotkey(self.hotkey, self.hotkey_pressed.emit)
            while self._is_running:
                self.msleep(100) # Just chill and wait for events.
        finally:
            # Clean up after ourselves.
            try:
                keyboard.remove_hotkey(self.hotkey)
            except (KeyError, ValueError):
                # This can happen if the hotkey was invalid to begin with. No biggie.
                pass

    def stop(self):
        """ Kills the thread gracefully. """
        self._is_running = False
        # Unregistering the hotkey will unblock the `keyboard.wait()` call,
        # but since we are using a loop, we just stop it.
        # A bit of a hack: send a dummy key event to unblock the thread immediately if needed.
        # For our msleep loop, it's not strictly necessary, but good practice.
        self.wait()


class ProcessLoaderThread(QThread):
    """
    A dedicated thread to fetch the list of processes without freezing the GUI.
    Emits a list of dictionaries, each containing a process name and PID.
    """
    processes_ready = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        process_list = []
        added_process_names = set()
        all_pids = psutil.pids()
        for pid in all_pids:
            try:
                p = psutil.Process(pid)
                p_name = p.name()
                
                # Filter out duplicates and processes without a command line
                if p_name.lower() in added_process_names or not p.cmdline():
                    continue

                added_process_names.add(p_name.lower())
                process_list.append({'name': p_name, 'pid': pid})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self.processes_ready.emit(process_list)


class IconLoaderThread(QThread):
    """
    A dedicated thread to load process icons in the background.
    This prevents the GUI from freezing while we fetch icons for all running processes.
    """
    icon_ready = pyqtSignal(QListWidgetItem, QIcon)

    def __init__(self, items_to_load, parent=None):
        super().__init__(parent)
        # A list of tuples: (QListWidgetItem, pid)
        self.items_to_load = items_to_load

    def run(self):
        for item, pid in self.items_to_load:
            try:
                process = psutil.Process(pid)
                exe_path = process.exe()
                if exe_path:
                    provider = QtWidgets.QFileIconProvider()
                    q_file_info = QtCore.QFileInfo(exe_path)
                    icon = provider.icon(q_file_info)
                    if not icon.isNull():
                        self.icon_ready.emit(item, icon)
            except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
                # Process might have terminated, or we don't have access. Skip it.
                continue


# --- UI Widgets ---

class BackgroundWidget(QWidget):
    """
    A custom widget that just plays our trippy background video.
    It receives frames from the VideoThread and paints them as its background.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frame = None
        self.video_thread = None

    def start_video(self):
        # Fire up the video thread if it's not already running.
        if self.video_thread and self.video_thread.isRunning():
            return
        self.video_thread = VideoThread(BG_VIDEO_PATH, self)
        self.video_thread.frame_ready.connect(self.set_frame)
        self.video_thread.start()
    
    def set_frame(self, image):
        """ Slot to receive a new frame from the video thread. """
        self.current_frame = image
        self.update() # Triggers a repaint.

    def paintEvent(self, event):
        """
        This is where the magic happens. We get the current frame and paint it.
        The `KeepAspectRatioByExpanding` and scaling ensures the video always fills
        the widget without getting distorted. It's like 'background-size: cover' in CSS.
        """
        painter = QPainter(self)
        if self.current_frame:
            target_rect = self.rect()
            scaled_image = self.current_frame.scaled(
                target_rect.size(), 
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                Qt.TransformationMode.SmoothTransformation
            )
            # Center the image inside the widget area.
            x = (target_rect.width() - scaled_image.width()) / 2
            y = (target_rect.height() - scaled_image.height()) / 2
            painter.drawImage(int(x), int(y), scaled_image)
        else:
            # If no video, just paint it black so it's not a glaring white spot.
            painter.fillRect(self.rect(), QBrush(QColor(0,0,0)))

    def stop_video(self):
        """ Gracefully stops the video thread. """
        if self.video_thread:
            self.video_thread.stop()


class CustomTitleBar(QWidget):
    """
    Our own little title bar. Because the default Windows one is boring.
    This gives us full control over the look and feel. Plus, it lets us do
    the whole "click and drag anywhere" thing.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(32)
        self.setObjectName("CustomTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(10)

        # App icon and title
        icon_label = QLabel(self)
        if os.path.exists(ICON_PATH):
            icon_label.setPixmap(QIcon(ICON_PATH).pixmap(18, 18))
        title_label = QLabel(self.parent_window.windowTitle(), self)

        # Window control buttons
        self.minimize_button = QPushButton("—")
        self.close_button = QPushButton("✕")
        self.minimize_button.setObjectName("TitleBarButton")
        self.close_button.setObjectName("TitleBarButton")
        
        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.close_button.clicked.connect(self.parent_window.close)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addStretch() # Pushes buttons to the right
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.close_button)
    
    # These next two methods are the secret sauce for making a frameless window draggable.
    def mousePressEvent(self, event):
        """ Grab the initial position when the user clicks. """
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_window.start_drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        """ Move the window as the user drags the mouse. """
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.parent_window.start_drag_pos
            self.parent_window.move(self.parent_window.x() + delta.x(), self.parent_window.y() + delta.y())
            self.parent_window.start_drag_pos = event.globalPosition().toPoint()


class ProcessDialog(QDialog):
    """
    This dialog pops up to let the user pick a process to mess with.
    It's a custom-styled dialog with our sexy video background, of course.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Process")
        self.setFixedSize(400, 500)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.selected_process = None
        self.start_drag_pos = None # For dragging the dialog

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(1, 1, 1, 1)
        dialog_layout.setSpacing(0)

        title_bar = CustomTitleBar(self)
        self.content_widget = BackgroundWidget(self)
        
        dialog_layout.addWidget(title_bar)
        dialog_layout.addWidget(self.content_widget)

        # Layout for the actual controls (list, buttons)
        controls_layout = QVBoxLayout(self.content_widget)
        controls_layout.setContentsMargins(15, 15, 15, 15)
        controls_layout.setSpacing(10)

        self.process_list_widget = QListWidget()
        controls_layout.addWidget(self.process_list_widget)

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        controls_layout.addLayout(button_layout)
        
        # Display a loading message instantly
        self.process_list_widget.addItem("Loading processes...")
        self.ok_button.setEnabled(False)

    def accept(self):
        """ When the user clicks OK. """
        if self.process_list_widget.currentItem():
            # We store the process name in the item's text.
            self.selected_process = self.process_list_widget.currentItem().text()
        self.content_widget.stop_video()
        super().accept()

    def reject(self):
        """ When the user clicks Cancel. """
        self.content_widget.stop_video()
        super().reject()

    def closeEvent(self, event):
        """ Make sure we stop the video even if the user closes the window. """
        self.content_widget.stop_video()
        super().closeEvent(event)

    def get_icon_for_process(self, process):
        """
        Attempts to get the icon for a given psutil.Process object.
        It's safer to use Qt's built-in icon provider.
        """
        try:
            exe_path = process.exe()
            if exe_path:
                provider = QtWidgets.QFileIconProvider()
                q_file_info = QtCore.QFileInfo(exe_path)
                icon = provider.icon(q_file_info)
                if not icon.isNull():
                    return icon
        except (psutil.AccessDenied, FileNotFoundError, psutil.NoSuchProcess):
            # This can happen for system processes or processes that terminate quickly.
            pass
        # If we fail for any reason, return the app's own icon as a fallback.
        return QIcon(ICON_PATH)

    @QtCore.pyqtSlot(list)
    def update_process_list(self, processes):
        """
        Slot to receive the process list from the ProcessLoaderThread.
        This populates the list widget and then starts the icon loading.
        """
        self.process_list_widget.clear() # Remove "Loading..."
        
        if not processes:
            self.process_list_widget.addItem("Could not load processes.")
            return

        items_for_icon_loader = []
        for p_info in sorted(processes, key=lambda x: x['name'].lower()):
            # Create item with a placeholder icon for now
            item = QListWidgetItem(QIcon(ICON_PATH), p_info['name'])
            item.setData(Qt.ItemDataRole.UserRole, p_info['pid'])
            self.process_list_widget.addItem(item)
            items_for_icon_loader.append((item, p_info['pid']))
        
        self.ok_button.setEnabled(True)
        self.start_icon_loader(items_for_icon_loader)

    def start_icon_loader(self, items_to_load):
        """ Starts the background thread to load icons for the visible items. """
        if not items_to_load:
            return
            
        self.icon_thread = IconLoaderThread(items_to_load, self)
        self.icon_thread.icon_ready.connect(self.update_item_icon)
        self.icon_thread.start()

    @QtCore.pyqtSlot(QListWidgetItem, QIcon)
    def update_item_icon(self, item, icon):
        """ Slot to receive an icon from the worker thread and apply it. """
        if item and self.process_list_widget.findItems(item.text(), Qt.MatchFlag.MatchExactly):
             item.setIcon(icon)

    def showEvent(self, event):
        """ 
        Overrides showEvent to start the expensive process loading *after* the dialog is visible.
        This makes the dialog appear instantly.
        """
        super().showEvent(event)
        self.content_widget.start_video()
        
        # Start the process loader thread, which will then trigger the icon loader
        self.process_loader_thread = ProcessLoaderThread(self)
        self.process_loader_thread.processes_ready.connect(self.update_process_list)
        self.process_loader_thread.start()


class MainWindow(QMainWindow):
    """
    The main application window. The mothership.
    It holds everything together: the main UI, the tray icon, the hotkey listener,
    and the core logic for killing connections.
    """
    hotkey_captured_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Connection Breaker")
        self.setFixedSize(400, 282)
        # We're drawing our own title bar, so get rid of the default one.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.start_drag_pos = None

        # App state
        self.selected_process = None
        self.current_hotkey = None
        self.hotkey_listener = None
        self.hotkey_capture_thread = None
        self.is_paused = False
        self.video_started = False # Optimization flag

        self.hotkey_captured_signal.connect(self.set_new_hotkey)

        # Set the main icon for the window and tray
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # --- UI Setup ---
        # We have a main widget that contains the title bar and the content area.
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)

        title_bar = CustomTitleBar(self)
        self.content_widget = BackgroundWidget()
        self.content_widget.start_video()
        
        main_layout.addWidget(title_bar)
        main_layout.addWidget(self.content_widget)
        self.setCentralWidget(main_widget)

        # The content area has a horizontal layout to split the menu from... well, nothing.
        # But it's good for alignment.
        outer_layout = QHBoxLayout(self.content_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # This is our main menu panel on the left.
        menu_widget = QWidget()
        menu_widget.setFixedWidth(280)
        
        menu_layout = QVBoxLayout(menu_widget)
        menu_layout.setContentsMargins(20, 35, 20, 35)
        menu_layout.setSpacing(15)
        menu_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.process_label = QLabel("No process selected")
        self.select_process_button = QPushButton("Select Process")
        self.set_hotkey_button = QPushButton("Set Hotkey")

        self.process_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.process_label.setWordWrap(True)

        self.select_process_button.clicked.connect(self.open_process_dialog)
        self.set_hotkey_button.clicked.connect(self.start_hotkey_capture)

        menu_layout.addWidget(self.process_label)
        menu_layout.addWidget(self.select_process_button)
        menu_layout.addWidget(self.set_hotkey_button)
        
        outer_layout.addWidget(menu_widget)
        outer_layout.addStretch() # Pushes the menu to the left

        # Fire up the system tray icon
        self.create_tray_icon()
        
    def showEvent(self, event):
        """
        Start expensive operations like video playback only when the window is first shown.
        """
        super().showEvent(event)
        if not self.video_started:
            self.content_widget.start_video()
            self.video_started = True

    def open_process_dialog(self):
        """ Opens the process selection dialog and updates the label. """
        dialog = ProcessDialog(self)
        if dialog.exec():
            if dialog.selected_process:
                self.selected_process = dialog.selected_process
                self.process_label.setText(f"Target: {self.selected_process}")
                # Start listening for the hotkey only after a process is selected
                if not self.hotkey_listener or not self.hotkey_listener.isRunning():
                    self.restart_hotkey_listener()
        else:
            if not self.selected_process:
                self.process_label.setText("No process selected")

    def create_tray_icon(self):
        """ Creates the system tray icon and its context menu. """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray not available. Bailing on tray icon.")
            return
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_PATH):
            self.tray_icon.setIcon(QIcon(ICON_PATH))
        
        self.tray_menu = QMenu()
        
        # Action to pause/resume the connection killing
        self.toggle_action = QAction("Pause", self)
        self.toggle_action.triggered.connect(self.toggle_pause)
        
        # Action to GTFO
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.exit_app)
        
        self.tray_menu.addAction(self.toggle_action)                             
        self.tray_menu.addAction(self.exit_action)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        """ Shows/hides the main window when the tray icon is clicked. """
        # A left-click on the tray icon.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isHidden():
                self.showNormal()
                self.activateWindow()
            else:
                self.hide()

    def toggle_pause(self):
        """ Toggles the paused state of the hotkey. """
        self.is_paused = not self.is_paused
        self.toggle_action.setText("Resume" if self.is_paused else "Pause")

    def exit_app(self):
        """ Cleans up and exits the application. """
        print("Attempting to exit...")
        self.tray_icon.hide()
        
        # Stop threads forcefully but gracefully
        if self.hotkey_listener and self.hotkey_listener.isRunning():
            self.hotkey_listener.stop()
            self.hotkey_listener.wait(1000) # Wait up to 1 sec
        
        # This is a big one. The keyboard library's hooks can prevent exit.
        # We remove all hooks to be sure.
        keyboard.unhook_all()

        if self.content_widget and self.content_widget.video_thread:
            self.content_widget.stop_video()
            self.content_widget.video_thread.wait(1000)

        print("Threads stopped, quitting application.")
        QApplication.instance().quit()
        # For stubborn cases, a hard exit might be needed, but quit() should work now.
        # os._exit(0)

    def kill_connections(self):
        """
        The main event. This is what the hotkey triggers.
        It runs the cports.exe command-line tool to nuke all connections
        for the selected process.
        """
        if self.is_paused or not self.selected_process:
            return
            
        if not os.path.exists(CPORTS_PATH):
            print(f"Can't find cports.exe at {CPORTS_PATH}. Can't do my job.")
            return
            
        try:
            # The command to close all TCP/UDP connections for the process.
            # We run this silently (CREATE_NO_WINDOW) so the user doesn't see a scary console pop up.
            command = [CPORTS_PATH, "/close", "*", "*", "*", "*", self.selected_process]
            subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except (subprocess.CalledProcessError, Exception) as e:
            # Something went wrong. It happens. We just log it and move on.
            print(f"Failed to kill connections for {self.selected_process}. Error: {e}")
            pass

    def start_hotkey_capture(self):
        """
        Temporarily disables the hotkey button and waits for the user to press a key combo.
        This is done in a separate thread so it doesn't freeze the GUI.
        """
        self.set_hotkey_button.setText("Press any key...")
        self.set_hotkey_button.setEnabled(False)
        
        # The worker function that will run in the thread.
        def capture_worker():
            # This is a blocking call, hence the need for a thread.
            hotkey = keyboard.read_hotkey(suppress=False)
            self.hotkey_captured_signal.emit(hotkey)

        self.hotkey_capture_thread = threading.Thread(target=capture_worker, daemon=True)
        self.hotkey_capture_thread.start()
        
    def set_new_hotkey(self, hotkey):
        """
        Once a hotkey is captured, this method processes it, validates it, translates it,
        and restarts the listener with the new hotkey.
        """
        hotkey_lower = hotkey.lower() if hotkey else ""
        self.set_hotkey_button.setEnabled(True)
        original_text = f"Hotkey: {self.current_hotkey.upper()}" if self.current_hotkey else "Set Hotkey"

        if not hotkey or hotkey_lower in ['esc', 'backspace']:
            self.current_hotkey = None
        else:
            MODIFIERS = {'ctrl', 'alt', 'shift', 'win'}
            parts = [p.strip() for p in hotkey_lower.split('+')]
            
            modifier_keys = [p for p in parts if p in MODIFIERS]
            non_modifier_keys = [p for p in parts if p not in MODIFIERS]

            # Rule 1: Hard error if more than one modifier is used.
            if len(modifier_keys) > 1:
                self.set_hotkey_button.setText("Too many modifiers!")
                QTimer.singleShot(2000, lambda: self.set_hotkey_button.setText(original_text))
                return

            # Rule 2: If multiple non-modifier keys are pressed, just use the last one.
            if len(non_modifier_keys) > 1:
                # e.g., 'a+d' becomes just 'd'. 'ctrl+a+d' becomes 'ctrl+d'.
                final_hotkey_parts = modifier_keys + [non_modifier_keys[-1]]
            elif not non_modifier_keys and len(modifier_keys) > 0:
                # User pressed only modifiers (e.g., 'ctrl+alt'), which is invalid.
                self.set_hotkey_button.setText("Invalid Combination!")
                QTimer.singleShot(2000, lambda: self.set_hotkey_button.setText(original_text))
                return
            else:
                final_hotkey_parts = parts
            
            # Translate any Cyrillic characters.
            translated_parts = [RU_TO_EN_MAP.get(part, part) for part in final_hotkey_parts]
            self.current_hotkey = ' + '.join(translated_parts)

        # Restart the listener with the new hotkey (or stop it if hotkey is None)
        self.restart_hotkey_listener()
        
        # Update the button text to show the new hotkey.
        hotkey_text = f"Hotkey: {self.current_hotkey.upper()}" if self.current_hotkey else "Set Hotkey"
        self.set_hotkey_button.setText(hotkey_text)
        
    def start_hotkey_listener(self):
        """ Starts or restarts the global hotkey listener thread. """
        # Stop the old one if it's running.
        if self.hotkey_listener and self.hotkey_listener.isRunning():
            self.hotkey_listener.stop()
        
        # Start a new one if a hotkey is set.
        if self.current_hotkey:
            self.hotkey_listener = HotkeyListener(self.current_hotkey, self)
            self.hotkey_listener.hotkey_pressed.connect(self.kill_connections)
            self.hotkey_listener.start()

    def restart_hotkey_listener(self):
        """ A simple alias for starting the listener. """
        self.start_hotkey_listener()
        

def apply_stylesheet(app):
    """
    All our CSS-like styling goes here. It's way cleaner than setting styles
    on individual widgets. We use object names (#TitleBarButton) to target
    specific widgets.
    """
    app.setStyleSheet("""
        QMainWindow, QDialog {
            background-color: #181818;
        }
        #CustomTitleBar {
            background-color: #0A0A0A;
            color: #E0E0E0;
        }
        #TitleBarButton {
            background-color: transparent;
            color: #E0E0E0;
            border: none;
            font-size: 16px;
            font-weight: bold;
            padding: 0;
            padding-bottom: 2px;
        }
        #TitleBarButton:hover {
            color: #9D00FF;
        }
        #TitleBarButton:pressed {
            color: #8A2BE2;
        }
        QWidget {
            color: #E0E0E0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 15px;
        }
        QPushButton {
            background-color: #0A0A0A;
            color: #FFFFFF;
            border: 0px solid #555;
            padding: 15px;
            border-radius: 0px;
            font-weight: bold;
            min-height: 24px;
        }
        QPushButton:hover {
            background-color: #1E1E1E;
        }
        QPushButton:pressed {
            background-color: #000000;
        }
        QPushButton:focus {
            outline: none;
        }
        QLabel {
            padding: -2px;
            background-color: transparent;
            border-radius: 2px;
        }
        QListWidget {
            background-color: #141414;
            border: none;
            padding: 5px;
            border-radius: 0px;
            outline: none;
        }
        QListWidget::item {
            padding: 11px;
            border-radius: 0px;
        }
        QListWidget::item:hover {
            background-color: #3A3A3A;
        }
        QListWidget::item:selected {
            background-color: #9D00FF;
            color: #FFFFFF;
        }
        QMenu {
            background-color: #1A1A1A;
            border: 1px solid #444;
            color: #FFFFFF;
        }
        QMenu::item:selected {
            background-color: #9D00FF;
        }
    """)

# --- Main Execution ---

if __name__ == "__main__":
    # This is for Windows to show the correct icon in the taskbar. It's a weird quirk.
    myappid = 'mycompany.myproduct.connectionbreaker.1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # --- Admin Rights Check ---
    # This is a critical check. The application cannot function without admin rights.
    if not is_admin():
        ctypes.windll.user32.MessageBoxW(
            0, 
            "This application requires administrator privileges to view all processes and manage network connections.", 
            "Administrator Privileges Required", 
            0x10 | 0x0  # MB_ICONERROR | MB_OK
        )
        sys.exit(1)

    app = QApplication(sys.argv)
    
    # --- Single Instance Lock ---
    # Create a unique key for the shared memory block
    lock_key = "ConnectionBreaker_SingleInstance_Lock"
    shared_memory = QSharedMemory(lock_key)
    
    # Try to attach to the shared memory. If it works, another instance is running.
    if shared_memory.attach():
        # Using a QMessageBox to show a nice, clean error.
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText("ConnectionBreaker is already running.")
        error_box.setInformativeText("Please check your system tray or task manager.")
        error_box.setWindowTitle("Application Already Running")
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        if os.path.exists(ICON_PATH):
            error_box.setWindowIcon(QIcon(ICON_PATH))
        error_box.exec()
        sys.exit(0) # Exit gracefully
    else:
        # If attach failed, it means we are the first instance. Create the lock.
        if not shared_memory.create(1):
            # This is an edge case, but good to handle.
            print(f"Error: Could not create shared memory segment: {shared_memory.errorString()}")
            sys.exit(1)

    # This is crucial for our tray icon logic. We don't want the app to exit
    # when the main window is hidden, only when we explicitly call quit().
    app.setQuitOnLastWindowClosed(False) 
    
    apply_stylesheet(app)

    # Set the global fallback icon for the app.
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
        
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
