import requests
import json
import os
import math

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from plyer import gps, notification
from kivy.core.audio import SoundLoader
from kivy_garden.mapview import MapView, MapMarker, MapSource


class ColoredBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(rgba=(0.8, 1.0, 1.0, 1))  # Helles Türkis
            self.rect = RoundedRectangle(radius=[15], size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


import shutil


class GeoApp(App):
    suggestions_cache = {}
    suggestions_cache_limit = 50
    suggestions_cache_usage = {}
    def clear_map_cache(self):
        try:
            cache_dir = os.path.join(os.getcwd(), "cache")
            if os.path.exists(cache_dir):
                for f in os.listdir(cache_dir):
                    file_path = os.path.join(cache_dir, f)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                print("Karten-Cache im Ordner ./cache wurde gelöscht.")
        except Exception as e:
            print("Fehler beim Löschen des Caches:", e)
        except Exception as e:
            print("Fehler beim Löschen des Caches beim Start:", e)

    def build(self):
        self.clear_map_cache()
        self.notification_sound = SoundLoader.load("notification.wav")
        self.suggestion_event = None
        self.suggestions = []
        self.saved_targets = []
        self.testing = not self.is_gps_available()

        self.sm = ScreenManager()
        self.main_screen = Screen(name="main")

        root_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        from kivy.uix.floatlayout import FloatLayout
        top_inputs = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        top_inputs.bind(minimum_height=top_inputs.setter('height'))

        self.debug_label = Label(text="[Debug] Standortdaten: unbekannt", size_hint_y=None, height=30,
                                 color=(0.1, 0.5, 0.5, 1))

        self.address_input = TextInput(hint_text="Adresse eingeben", size_hint_y=None, height=50,
                                       background_color=(0.9, 1, 1, 1), foreground_color=(0, 0.3, 0.3, 1),
                                       padding=[10, 10, 10, 10], cursor_color=(0, 0.5, 0.5, 1))
        self.address_input.bind(text=self.on_address_text)

        self.radius_input = TextInput(hint_text="Entfernung in Metern", size_hint_y=None, height=50, input_filter='int',
                                      background_color=(0.9, 1, 1, 1), foreground_color=(0, 0.3, 0.3, 1),
                                      padding=[10, 10, 10, 10], cursor_color=(0, 0.5, 0.5, 1))

        self.suggestion_box = GridLayout(cols=1, size_hint_y=None)
        self.suggestion_box.bind(minimum_height=self.suggestion_box.setter('height'))
        self.suggestion_scroll = ScrollView(size_hint=(1, None), size=(100, 100))
        self.suggestion_scroll.add_widget(self.suggestion_box)

        save_button = Button(text="Adresse speichern", size_hint_y=None, height=50, background_color=(0.2, 0.6, 0.6, 1),
                             color=(1, 1, 1, 1))
        save_button.bind(on_press=self.save_address)

        self.result_label = Label(text="", size_hint_y=None, height=40, color=(0, 0.3, 0.3, 1))

        top_inputs.add_widget(self.address_input)
        top_inputs.add_widget(self.radius_input)
        top_inputs.add_widget(self.suggestion_scroll)
        top_inputs.add_widget(save_button)
        top_inputs.add_widget(self.result_label)
        top_inputs.add_widget(self.debug_label)

        middle_layout = BoxLayout(orientation='horizontal', spacing=10)

        self.target_list = GridLayout(cols=1, size_hint_y=None, spacing=5)
        self.target_list.bind(minimum_height=self.target_list.setter('height'))
        self.target_scroll = ScrollView(size_hint=(0.5, 1))
        self.target_scroll.add_widget(self.target_list)

        map_source = MapSource(
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            cache_key="osm",
            tile_size=256,
            image_ext="png",
            attribution="© OpenStreetMap contributors",
            min_zoom=1,
            max_zoom=19
        )
        self.map_view = MapView(zoom=13, lat=51.4424292, lon=7.3334361, size_hint=(0.5, 0.9), map_source=map_source)
        self.map_marker_self = MapMarker(lat=51.4424292, lon=7.3334361)

        # Marker wird einmalig hinzugefügt
        self.map_view.add_widget(self.map_marker_self)

        middle_layout.add_widget(self.target_scroll)
        middle_layout.add_widget(self.map_view)

        root_layout.add_widget(top_inputs)
        root_layout.add_widget(middle_layout)

        # App schließen Button
        close_button = Button(text="App schließen", size_hint_y=None, height=50, background_color=(0.6, 0.2, 0.2, 1), color=(1, 1, 1, 1))
        close_button.bind(on_press=self.stop)
        root_layout.add_widget(close_button)

        self.main_screen.add_widget(root_layout)
        self.sm.add_widget(self.main_screen)

        self.load_saved_targets()
        Clock.schedule_interval(self.check_all_targets, 30)

        # Karte zentrieren Button
        center_btn = Button(text="Karte zentrieren", size_hint=(None, None), size=(160, 40),
                            pos_hint={"right": 1, "y": 0}, background_color=(0.4, 0.7, 0.7, 1), color=(1, 1, 1, 1))
        center_btn.bind(on_press=self.center_map_on_self)
        self.map_view.add_widget(center_btn)

        return self.sm

    def is_gps_available(self):
        try:
            test = gps.get_location()
            return test is not None
        except:
            return False

    def get_current_location(self):
        if self.testing:
            return {'lat': 51.4424292, 'lon': 7.3334361}
        else:
            return gps.get_location()

    def on_address_text(self, instance, value):
        if self.suggestion_event:
            self.suggestion_event.cancel()
        if len(value) > 2:
            self.suggestion_event = Clock.schedule_once(lambda dt: self.fetch_suggestions(value), 0.5)
        else:
            self.suggestion_box.clear_widgets()
            self.suggestion_scroll.height = 0

    def fetch_suggestions(self, query):
        if query in self.suggestions_cache:
            self.suggestions_cache_usage[query] = Clock.get_time()
            self.suggestions = self.suggestions_cache[query]
            self.show_cached_suggestions()
            return

        self.suggestion_box.clear_widgets()
        url = "https://nominatim.openstreetmap.org/search"
        params = {'q': query, 'format': 'json', 'limit': 5, 'addressdetails': 1}
        headers = {'User-Agent': 'KivyGeoApp/1.0'}
        try:
            response = requests.get(url, params=params, headers=headers)
            data = response.json()
            self.suggestions = data
            self.suggestions_cache[query] = data
            self.suggestions_cache_usage[query] = Clock.get_time()
            if len(self.suggestions_cache) > self.suggestions_cache_limit:
                oldest = sorted(self.suggestions_cache_usage.items(), key=lambda x: x[1])[:len(self.suggestions_cache)//2]
                for key, _ in oldest:
                    self.suggestions_cache.pop(key, None)
                    self.suggestions_cache_usage.pop(key, None)
            for item in data:
                display_name = item['display_name']
                btn = Button(text=display_name, size_hint_y=None, height=40, background_color=(0.8, 1, 1, 1),
                             color=(0, 0.3, 0.3, 1))
                btn.bind(on_press=lambda inst, name=item['display_name']: self.select_suggestion(name))
                self.suggestion_box.add_widget(btn)
            self.suggestion_scroll.height = min(5, len(data)) * 40
        except Exception as e:
            print("Fehler bei Vorschlägen:", e)

    def show_cached_suggestions(self):
        self.suggestion_box.clear_widgets()
        for item in self.suggestions:
            display_name = item['display_name']
            btn = Button(text=display_name, size_hint_y=None, height=40, background_color=(0.8, 1, 1, 1),
                         color=(0, 0.3, 0.3, 1))
            btn.bind(on_press=lambda inst, name=item['display_name']: self.select_suggestion(name))
            self.suggestion_box.add_widget(btn)
        self.suggestion_scroll.height = min(5, len(self.suggestions)) * 40

    def select_suggestion(self, address_text):
        self.address_input.text = address_text
        self.suggestion_box.clear_widgets()
        self.result_label.text = f"Ausgewählt: {address_text}"

    def save_address(self, instance):
        address = self.address_input.text
        radius = self.radius_input.text
        if not address or not radius.isdigit():
            self.result_label.text = "Bitte Adresse und gültige Entfernung eingeben"
            return
        url = "https://nominatim.openstreetmap.org/search"
        params = {'q': address, 'format': 'json', 'limit': 1}
        headers = {'User-Agent': 'KivyGeoApp/1.0'}
        try:
            response = requests.get(url, params=params, headers=headers)
            data = response.json()
            if data:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                target = {
                    'address': address,
                    'lat': lat,
                    'lon': lon,
                    'radius': int(radius),
                    'inside': False
                }
                self.saved_targets.append(target)
                self.update_target_list()
                self.update_map_markers()
                self.save_to_file()
                self.result_label.text = "Adresse gespeichert."
            else:
                self.result_label.text = "Adresse nicht gefunden."
        except Exception as e:
            print("Fehler beim Speichern:", e)
            self.result_label.text = "Fehler bei der Abfrage"

    def update_target_list(self):
        self.target_list.clear_widgets()
        for i, target in enumerate(self.saved_targets):
            box = BoxLayout(size_hint_y=None, height=40)
            address_parts = target['address'].split(',')
            filtered = [part.strip() for part in address_parts if any(x in part.lower() for x in
                                                                      ['straße', 'str.', 'weg', 'gasse', 'allee',
                                                                       'platz']) or part.strip().isdigit() or len(
                part.strip()) == 5]
            short_address = ', '.join(filtered)
            label = Label(text=f"{short_address} ({target['radius']} m)", halign="left", color=(0, 0.2, 0.2, 1))
            btn = Button(text="Löschen", size_hint_x=None, width=100, height=40, background_color=(1, 0.4, 0.4, 1),
                         color=(1, 1, 1, 1))
            btn.bind(on_press=lambda inst, index=i: self.delete_target(index))
            box.add_widget(label)
            box.add_widget(btn)
            self.target_list.add_widget(box)

    def update_map_markers(self):
        # Nur Zielmarker entfernen, nicht Tiles oder eigenen Marker
        for child in list(self.map_view.children):
            if isinstance(child, MapMarker) and child is not self.map_marker_self:
                self.map_view.remove_widget(child)
        self.target_markers = []
        for target in self.saved_targets:
            marker = MapMarker(lat=target['lat'], lon=target['lon'])
            self.map_view.add_widget(marker)
            self.target_markers.append(marker)

    def delete_target(self, index):
        del self.saved_targets[index]
        self.update_target_list()
        self.update_map_markers()
        self.save_to_file()

    def save_to_file(self):
        try:
            with open("saved_targets.json", "w", encoding="utf-8") as f:
                json.dump(self.saved_targets, f, ensure_ascii=False, indent=2)
            print("Ziele gespeichert.")
        except Exception as e:
            print("Fehler beim Speichern in Datei:", e)

    def load_saved_targets(self):
        if os.path.exists("saved_targets.json"):
            try:
                with open("saved_targets.json", "r", encoding="utf-8") as f:
                    self.saved_targets = json.load(f)
                    self.update_target_list()
                    Clock.schedule_once(lambda dt: self.update_map_markers(), 1)
                    print("Ziele geladen.")
            except Exception as e:
                print("Fehler beim Laden:", e)

    def check_all_targets(self, dt):
        try:
            location = self.get_current_location()
            if not location:
                self.debug_label.text = "[Debug] Keine Standortdaten verfügbar."
                print("Keine Standortdaten verfügbar.")
                return
            current_lat = location['lat']
            current_lon = location['lon']
            self.debug_label.text = f"[Debug] Standort: {current_lat:.5f}, {current_lon:.5f}"
            self.map_marker_self.lat = current_lat
            self.map_marker_self.lon = current_lon

            for target in self.saved_targets:
                distance = self.haversine(target['lon'], target['lat'], current_lon, current_lat)
                print(f"{target['address']} - Entfernung: {int(distance)} m")

                if distance <= target['radius'] and not target.get('inside', False):
                    self.send_notification("In der Nähe", f"Du bist bei: {target['address']}")
                    target['inside'] = True
                elif distance > target['radius']:
                    target['inside'] = False

            self.save_to_file()
        except Exception as e:
            print("Fehler beim GPS-Check:", e)

    def haversine(self, lon1, lat1, lon2, lat2):
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def center_map_on_self(self, instance):
        location = self.get_current_location()
        if location:
            self.map_view.center_on(location['lat'], location['lon'])

    def send_notification(self, title, message):
        try:
            if self.notification_sound:
                self.notification_sound.play()
            notification.notify(title=title, message=message, timeout=5)
        except Exception as e:
            print("Fehler bei Notification:", e)


if __name__ == "__main__":
    GeoApp().run()
