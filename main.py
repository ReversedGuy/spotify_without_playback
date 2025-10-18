import sys
import sqlite3
import requests
import threading
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QTabWidget, QLineEdit, QPushButton, 
                               QLabel, QScrollArea, QFrame, QListWidget,
                               QListWidgetItem, QDialog, QComboBox, QDialogButtonBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap

class SearchWorker(QThread):
    finished = Signal(list)
    
    def __init__(self, query):
        super().__init__()
        self.query = query
    
    def run(self):
        try:
            params = {'term': self.query, 'media': 'music', 'entity': 'song', 'limit': 20}
            response = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
            data = response.json()
            results = []
            
            for item in data.get('results', []):
                features = item.get('features', [])
                results.append({
                    'title': item.get('trackName', 'Unknown'),
                    'artist': item.get('artistName', 'Unknown'),
                    'year': int(item.get('releaseDate', '1900')[:4]) if item.get('releaseDate') else 1900,
                    'cover_url': item.get('artworkUrl100', '').replace('100x100', '400x400'),
                    'features': ', '.join(features) if features else '',
                    'api_id': str(item.get('trackId', ''))
                })
            self.finished.emit(results)
        except:
            self.finished.emit([])

class CreatePlaylistDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Playlist")
        self.setFixedSize(300, 150)
        self.setStyleSheet("background-color: #140214; color: white;")
        
        layout = QVBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter playlist name...")
        self.name_input.setStyleSheet("padding: 8px; border: 2px solid #ff2a9d; border-radius: 6px; background-color: #2a082a; color: white;")
        
        layout.addWidget(QLabel("Playlist Name:"))
        layout.addWidget(self.name_input)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("QPushButton { background-color: #ff2a9d; color: white; border: none; padding: 8px 16px; border-radius: 6px; }")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def get_playlist_name(self):
        return self.name_input.text().strip()  # Fixed: changed search_input to name_input
      
# *******************************************************************************************************
class MusicDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('music_app.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS songs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, artist TEXT NOT NULL, year INTEGER, cover_url TEXT, features TEXT, api_id TEXT UNIQUE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS playlist_songs (playlist_id INTEGER, song_id INTEGER, PRIMARY KEY (playlist_id, song_id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS liked_songs (song_id INTEGER UNIQUE)')
        self.conn.commit()
    
    def add_song(self, song_data):
        cursor = self.conn.cursor()
        try:
            cursor.execute('INSERT OR IGNORE INTO songs (title, artist, year, cover_url, features, api_id) VALUES (?, ?, ?, ?, ?, ?)',
                         (song_data['title'], song_data['artist'], song_data['year'], song_data['cover_url'], song_data['features'], song_data['api_id']))
            self.conn.commit()
            cursor.execute('SELECT id FROM songs WHERE api_id = ?', (song_data['api_id'],))
            result = cursor.fetchone()
            return result[0] if result else None
        except:
            return None
    
    def create_playlist(self, name):
        try:
            self.conn.cursor().execute('INSERT INTO playlists (name) VALUES (?)', (name,))
            self.conn.commit()
            return True
        except:
            return False
    
    def get_playlists(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, name FROM playlists')
        return [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    
    def add_song_to_playlist(self, song_id, playlist_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)', (playlist_id, song_id))
            self.conn.commit()
            return cursor.rowcount > 0
        except:
            return False
    
    def like_song(self, song_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO liked_songs (song_id) VALUES (?)', (song_id,))
            self.conn.commit()
            return cursor.rowcount > 0
        except:
            return False
    
    def get_playlist_songs(self, playlist_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT s.id, s.title, s.artist, s.year, s.cover_url, s.features FROM songs s JOIN playlist_songs ps ON s.id = ps.song_id WHERE ps.playlist_id = ?', (playlist_id,))
        return [{'id': row[0], 'title': row[1], 'artist': row[2], 'year': row[3], 'cover_url': row[4], 'features': row[5]} for row in cursor.fetchall()]
    
    def get_liked_songs(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT s.id, s.title, s.artist, s.year, s.cover_url, s.features FROM songs s JOIN liked_songs ls ON s.id = ls.song_id')
        return [{'id': row[0], 'title': row[1], 'artist': row[2], 'year': row[3], 'cover_url': row[4], 'features': row[5]} for row in cursor.fetchall()]
    
    def remove_from_playlist(self, song_id, playlist_id):
        self.conn.cursor().execute('DELETE FROM playlist_songs WHERE song_id = ? AND playlist_id = ?', (song_id, playlist_id))
        self.conn.commit()
    
    def remove_from_liked(self, song_id):
        self.conn.cursor().execute('DELETE FROM liked_songs WHERE song_id = ?', (song_id,))
        self.conn.commit()
#******************************************************************************************************

class SongWidget(QFrame):
    def __init__(self, song_data, show_remove=False, playlist_id=None, db=None, parent_tab=None):
        super().__init__()
        self.song_data = song_data
        self.playlist_id = playlist_id
        self.db = db
        self.parent_tab = parent_tab
        self.setup_ui(show_remove)
        self.load_cover()
    
    def setup_ui(self, show_remove):
        self.setStyleSheet("QFrame { background-color: #2a082a; border-radius: 8px; padding: 12px; margin: 4px; }")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Larger cover art (100x100)
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(100, 100)
        self.cover_label.setStyleSheet("QLabel { background-color: #3d0a3d; border-radius: 8px; }")
        self.cover_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cover_label)
        
        # Song info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        title_label = QLabel(self.song_data['title'])
        title_label.setStyleSheet("font-weight: bold; color: white; font-size: 14px;")
        artist_label = QLabel(f"by {self.song_data['artist']}")
        artist_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        year_label = QLabel(f"Released: {self.song_data.get('year', 'Unknown')}")
        year_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        
        info_layout.addWidget(title_label)
        info_layout.addWidget(artist_label)
        info_layout.addWidget(year_label)
        
        if self.song_data.get('features'):
            features_label = QLabel(f"Featuring: {self.song_data['features']}")
            features_label.setStyleSheet("color: #ff2a9d; font-size: 11px;")
            info_layout.addWidget(features_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        if show_remove:
            remove_btn = QPushButton("Remove")
            remove_btn.setStyleSheet("QPushButton { background-color: #ff2a9d; color: white; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }")
            remove_btn.clicked.connect(self.remove_song)
            layout.addWidget(remove_btn)
        
        self.setLayout(layout)
    
    def load_cover(self):
        if self.song_data.get('cover_url'):
            threading.Thread(target=self._load_cover_thread, daemon=True).start()
    
    def _load_cover_thread(self):
        try:
            response = requests.get(self.song_data['cover_url'], timeout=5)
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            scaled_pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cover_label.setPixmap(scaled_pixmap)
        except:
            pass
    
    def remove_song(self):
        if self.playlist_id and self.db:
            self.db.remove_from_playlist(self.song_data['id'], self.playlist_id)
        elif self.db:
            self.db.remove_from_liked(self.song_data['id'])
        
        if self.parent_tab:
            self.parent_tab.refresh_content()
        
        self.setParent(None)

class SearchResultWidget(QFrame):
    def __init__(self, song_data, db, parent_tab):
        super().__init__()
        self.song_data = song_data
        self.db = db
        self.parent_tab = parent_tab
        self.setup_ui()
        self.load_cover()
    
    def setup_ui(self):
        self.setStyleSheet("QFrame { background-color: #2a082a; border-radius: 10px; padding: 15px; margin: 8px 4px; }")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Larger cover art (120x120)
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(120, 120)
        self.cover_label.setStyleSheet("QLabel { background-color: #3d0a3d; border-radius: 10px; }")
        self.cover_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cover_label)
        
        # Song info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        
        title_label = QLabel(self.song_data['title'])
        title_label.setStyleSheet("font-weight: bold; color: white; font-size: 16px;")
        artist_label = QLabel(f"Artist: {self.song_data['artist']}")
        artist_label.setStyleSheet("color: #cccccc; font-size: 14px;")
        year_label = QLabel(f"Year: {self.song_data.get('year', 'Unknown')}")
        year_label.setStyleSheet("color: #cccccc; font-size: 13px;")
        
        info_layout.addWidget(title_label)
        info_layout.addWidget(artist_label)
        info_layout.addWidget(year_label)
        
        if self.song_data.get('features'):
            features_label = QLabel(f"Features: {self.song_data['features']}")
            features_label.setStyleSheet("color: #ff2a9d; font-size: 13px;")
            info_layout.addWidget(features_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Action buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(6)
        
        like_btn = QPushButton("❤️ Like")
        like_btn.setStyleSheet("QPushButton { background-color: #ff2a9d; color: white; border: none; padding: 8px 12px; border-radius: 6px; font-weight: bold; }")
        like_btn.clicked.connect(self.like_song)
        
        playlist_btn = QPushButton("➕ Playlist")
        playlist_btn.setStyleSheet("QPushButton { background-color: #9d4edd; color: white; border: none; padding: 8px 12px; border-radius: 6px; font-weight: bold; }")
        playlist_btn.clicked.connect(self.add_to_playlist)
        
        button_layout.addWidget(like_btn)
        button_layout.addWidget(playlist_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_cover(self):
        if self.song_data.get('cover_url'):
            threading.Thread(target=self._load_cover_thread, daemon=True).start()
    
    def _load_cover_thread(self):
        try:
            response = requests.get(self.song_data['cover_url'], timeout=5)
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            scaled_pixmap = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cover_label.setPixmap(scaled_pixmap)
        except:
            pass
    
    def like_song(self):
        song_id = self.db.add_song(self.song_data)
        if song_id:
            self.db.like_song(song_id)
            self.parent_tab.main_window.refresh_all_tabs()
    
    def add_to_playlist(self):
        playlists = self.db.get_playlists()
        if not playlists:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add to Playlist")
        dialog.setFixedSize(250, 120)
        dialog.setStyleSheet("background-color: #140214; color: white;")
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select Playlist:"))
        
        combo = QComboBox()
        combo.setStyleSheet("QComboBox { background-color: #2a082a; color: white; border: 2px solid #ff2a9d; border-radius: 4px; padding: 5px; }")
        for playlist in playlists:
            combo.addItem(playlist['name'], playlist['id'])
        layout.addWidget(combo)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("QPushButton { background-color: #ff2a9d; color: white; border: none; padding: 6px 12px; border-radius: 4px; }")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            song_id = self.db.add_song(self.song_data)
            if song_id:
                self.db.add_song_to_playlist(song_id, combo.currentData())

class BaseTab(QWidget):
    def __init__(self, db, main_window):
        super().__init__()
        self.db = db
        self.main_window = main_window
    
    def clear_layout(self, layout):
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

class ExploreTab(BaseTab):
    def __init__(self, db, main_window):
        super().__init__(db, main_window)
        self.search_worker = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Search section
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for songs, artists...")
        self.search_input.setStyleSheet("QLineEdit { padding: 12px; border: 2px solid #ff2a9d; border-radius: 8px; background-color: #2a082a; color: white; }")
        self.search_input.returnPressed.connect(self.search_songs)
        
        search_btn = QPushButton("Search")
        search_btn.setStyleSheet("QPushButton { background-color: #ff2a9d; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; }")
        search_btn.clicked.connect(self.search_songs)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)
        
        # Results area
        self.results_scroll = QScrollArea()
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_layout.setSpacing(10)
        
        self.results_scroll.setWidget(self.results_widget)
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setStyleSheet("QScrollArea { border: none; background-color: #140214; }")
        
        layout.addWidget(self.results_scroll)
        self.setLayout(layout)
    
    def search_songs(self):
        query = self.search_input.text().strip()
        if not query:
            return
        
        self.clear_layout(self.results_layout)
        loading_label = QLabel("Searching...")
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setStyleSheet("color: #ff2a9d; font-size: 16px; font-weight: bold;")
        self.results_layout.addWidget(loading_label)
        
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()
        
        self.search_worker = SearchWorker(query)
        self.search_worker.finished.connect(self.display_results)
        self.search_worker.start()
    
    def display_results(self, results):
        self.clear_layout(self.results_layout)
        
        if not results:
            no_results = QLabel("No results found")
            no_results.setAlignment(Qt.AlignCenter)
            no_results.setStyleSheet("color: #ff2a9d; font-size: 16px; font-weight: bold;")
            self.results_layout.addWidget(no_results)
            return
        
        for song_data in results:
            self.results_layout.addWidget(SearchResultWidget(song_data, self.db, self))

class PlaylistsTab(BaseTab):
    def __init__(self, db, main_window):
        super().__init__(db, main_window)
        self.current_playlist_id = None
        self.setup_ui()
        self.load_playlists()
    
    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Left panel
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        
        left_panel.addWidget(QLabel("Your Playlists", styleSheet="color: #ff2a9d; font-size: 18px; font-weight: bold;"))
        
        self.playlists_list = QListWidget(styleSheet="""
            QListWidget { background-color: #2a082a; border: 2px solid #ff2a9d; border-radius: 8px; color: white; }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #3d0a3d; }
            QListWidget::item:selected { background-color: #ff2a9d; }
        """)
        self.playlists_list.itemClicked.connect(self.on_playlist_selected)
        left_panel.addWidget(self.playlists_list)
        
        create_btn = QPushButton("Create New Playlist", styleSheet="QPushButton { background-color: #9d4edd; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; }")
        create_btn.clicked.connect(self.create_playlist)
        left_panel.addWidget(create_btn)
        
        # Right panel
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)
        
        right_panel.addWidget(QLabel("Songs in Playlist", styleSheet="color: #ff2a9d; font-size: 18px; font-weight: bold;"))
        
        self.songs_scroll = QScrollArea()
        self.songs_widget = QWidget()
        self.songs_layout = QVBoxLayout(self.songs_widget)
        self.songs_layout.setAlignment(Qt.AlignTop)
        self.songs_layout.setSpacing(8)
        
        self.songs_scroll.setWidget(self.songs_widget)
        self.songs_scroll.setWidgetResizable(True)
        self.songs_scroll.setStyleSheet("QScrollArea { border: none; background-color: #140214; }")
        right_panel.addWidget(self.songs_scroll)
        
        layout.addLayout(left_panel, 1)
        layout.addLayout(right_panel, 2)
        self.setLayout(layout)
    
    def load_playlists(self):
        self.playlists_list.clear()
        for playlist in self.db.get_playlists():
            item = QListWidgetItem(playlist['name'])
            item.setData(Qt.UserRole, playlist['id'])
            self.playlists_list.addItem(item)
    
    def create_playlist(self):
        dialog = CreatePlaylistDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.get_playlist_name():
            self.db.create_playlist(dialog.get_playlist_name())
            self.load_playlists()
            self.main_window.refresh_all_tabs()
    
    def on_playlist_selected(self, item):
        self.current_playlist_id = item.data(Qt.UserRole)
        self.refresh_content()
    
    def refresh_content(self):
        self.clear_layout(self.songs_layout)
        
        if not self.current_playlist_id:
            self.songs_layout.addWidget(QLabel("Select a playlist to view songs", alignment=Qt.AlignCenter, styleSheet="color: #ff2a9d; font-size: 16px;"))
            return
        
        songs = self.db.get_playlist_songs(self.current_playlist_id)
        
        if not songs:
            self.songs_layout.addWidget(QLabel("No songs in this playlist", alignment=Qt.AlignCenter, styleSheet="color: #ff2a9d; font-size: 16px;"))
            return
        
        for song_data in songs:
            self.songs_layout.addWidget(SongWidget(song_data, show_remove=True, playlist_id=self.current_playlist_id, db=self.db, parent_tab=self))

class LikedTab(BaseTab):
    def __init__(self, db, main_window):
        super().__init__(db, main_window)
        self.setup_ui()
        self.refresh_content()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        layout.addWidget(QLabel("Your Liked Songs", styleSheet="color: #ff2a9d; font-size: 18px; font-weight: bold;"))
        
        self.songs_scroll = QScrollArea()
        self.songs_widget = QWidget()
        self.songs_layout = QVBoxLayout(self.songs_widget)
        self.songs_layout.setAlignment(Qt.AlignTop)
        self.songs_layout.setSpacing(8)
        
        self.songs_scroll.setWidget(self.songs_widget)
        self.songs_scroll.setWidgetResizable(True)
        self.songs_scroll.setStyleSheet("QScrollArea { border: none; background-color: #140214; }")
        
        layout.addWidget(self.songs_scroll)
        self.setLayout(layout)
    
    def refresh_content(self):
        self.clear_layout(self.songs_layout)
        
        songs = self.db.get_liked_songs()
        
        if not songs:
            self.songs_layout.addWidget(QLabel("No liked songs yet", alignment=Qt.AlignCenter, styleSheet="color: #ff2a9d; font-size: 16px; font-weight: bold;"))
            return
        
        for song_data in songs:
            self.songs_layout.addWidget(SongWidget(song_data, show_remove=True, db=self.db, parent_tab=self))

class MusicApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = MusicDatabase()
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Modern Music Player")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("background-color: #140214;")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget(styleSheet="""
            QTabWidget::pane { border: none; background-color: #140214; }
            QTabBar::tab { background-color: #2a082a; color: white; padding: 12px 24px; margin-right: 4px; border-radius: 8px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #ff2a9d; }
        """)
        
        self.explore_tab = ExploreTab(self.db, self)
        self.playlists_tab = PlaylistsTab(self.db, self)
        self.liked_tab = LikedTab(self.db, self)
        
        self.tabs.addTab(self.explore_tab, "🎵 Search/Explore")
        self.tabs.addTab(self.playlists_tab, "📋 Playlists")
        self.tabs.addTab(self.liked_tab, "❤️  Liked")
        
        layout.addWidget(self.tabs)
    
    def refresh_all_tabs(self):
        self.playlists_tab.load_playlists()
        if self.playlists_tab.current_playlist_id:
            self.playlists_tab.refresh_content()
        self.liked_tab.refresh_content()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MusicApp()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
