#!/usr/bin/env python3
"""
Standalone Internet Connectivity Monitor
Monitors internet connectivity and logs data to Google Sheets
No Docker required - runs directly on Windows, Mac, or Linux

Requirements:
- Python 3.7+
- Google Sheets API credentials (service_account.json)
- Required Python packages (auto-installed)

Usage:
1. Install Python 3.7+
2. Download this script
3. Configure settings below
4. Place service_account.json in same directory
5. Run: python internet_monitor.py
"""

# =============================================================================
# CONFIGURATION SECTION - EDIT THESE VALUES AS NEEDED
# =============================================================================

# Basic Settings
LOCATION_ID = "house1"                    # Unique identifier for this location
CHECK_INTERVAL = 60                       # How often to check connectivity (seconds)
GOOGLE_SPREADSHEET_ID = "<replace-me>"                # Your Google Spreadsheet ID (required)

# Timeout Settings (seconds)
PING_TIMEOUT = 5                          # Ping timeout
HTTP_TIMEOUT = 5                          # HTTP request timeout
DNS_TIMEOUT = 5                           # DNS resolution timeout

# Test Targets
PING_TARGETS = [                          # Servers to ping test
    '8.8.8.8',          # Google DNS
    '1.1.1.1',          # Cloudflare DNS
    '208.67.222.222'    # OpenDNS
]

HTTP_TARGETS = [                          # Websites to test HTTP connectivity
    'https://google.com',
    'https://cloudflare.com',
    'https://github.com'
]

DNS_SERVERS = [                           # DNS servers to test resolution
    '8.8.8.8',          # Google DNS
    '1.1.1.1'           # Cloudflare DNS
]

# Service Account File (must be in same directory as this script)
SERVICE_ACCOUNT_FILE = 'service_account.json'

# =============================================================================
# CONFIGURATION EXAMPLES - Choose settings based on your needs
# =============================================================================
"""
Fast Outage Detection:
LOCATION_ID = "home_fast"
CHECK_INTERVAL = 15       # Check every 15 seconds
PING_TIMEOUT = 3          # Quick timeouts
HTTP_TIMEOUT = 3
DNS_TIMEOUT = 3

Standard Home Monitoring:
LOCATION_ID = "house1"
CHECK_INTERVAL = 60       # Check every minute
PING_TIMEOUT = 5          # Standard timeouts
HTTP_TIMEOUT = 5
DNS_TIMEOUT = 5

Slow Connection Monitoring:
LOCATION_ID = "remote_office"
CHECK_INTERVAL = 120      # Check every 2 minutes
PING_TIMEOUT = 10         # Longer timeouts
HTTP_TIMEOUT = 15
DNS_TIMEOUT = 10

Multiple Locations (use same spreadsheet ID):
Location 1: LOCATION_ID = "house1"
Location 2: LOCATION_ID = "house2"
Location 3: LOCATION_ID = "office"
"""

# =============================================================================
# DO NOT EDIT BELOW THIS LINE UNLESS YOU KNOW WHAT YOU'RE DOING
# =============================================================================

import os
import sys
import time
import json
import subprocess
import platform
import socket
import urllib.request
import urllib.error
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging
from pathlib import Path
import importlib.util

# Auto-install required packages
def install_package(package_name, import_name=None):
    """Install package if not available"""
    if import_name is None:
        import_name = package_name
    
    try:
        if import_name == 'google.auth':
            import google.auth
        elif import_name == 'googleapiclient':
            import googleapiclient
        elif import_name == 'dns.resolver':
            import dns.resolver
        else:
            __import__(import_name)
        return True
    except ImportError:
        print(f"Installing {package_name}...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
            return True
        except subprocess.CalledProcessError:
            print(f"Failed to install {package_name}. Please install manually:")
            print(f"pip install {package_name}")
            return False

# Install required packages
required_packages = [
    ('google-auth', 'google.auth'),
    ('google-auth-oauthlib', 'google.auth'),
    ('google-auth-httplib2', 'google.auth'),
    ('google-api-python-client', 'googleapiclient'),
    ('dnspython', 'dns.resolver'),
    ('requests', 'requests'),
]

print("Checking required packages...")
missing_packages = []
for package, import_name in required_packages:
    if not install_package(package, import_name):
        missing_packages.append(package)

if missing_packages:
    print(f"Failed to install: {', '.join(missing_packages)}")
    print("Please install them manually and run the script again.")
    sys.exit(1)

# Now import all required modules
import requests
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
class Config:
    def __init__(self):
        # Use the configuration values from the top of the file
        self.LOCATION_ID = os.getenv('LOCATION_ID', LOCATION_ID)
        self.CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', CHECK_INTERVAL))
        self.GOOGLE_SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID', GOOGLE_SPREADSHEET_ID)
        self.SERVICE_ACCOUNT_FILE = SERVICE_ACCOUNT_FILE
        
        # Timeout settings
        self.PING_TIMEOUT = PING_TIMEOUT
        self.HTTP_TIMEOUT = HTTP_TIMEOUT  
        self.DNS_TIMEOUT = DNS_TIMEOUT
        
        # Test targets
        self.PING_TARGETS = PING_TARGETS.copy()
        self.HTTP_TARGETS = HTTP_TARGETS.copy()
        self.DNS_SERVERS = DNS_SERVERS.copy()
        
        # Local storage
        self.DATA_DIR = Path('monitor_data')
        self.LOG_FILE = self.DATA_DIR / 'monitor.log'
        self.BACKUP_FILE = self.DATA_DIR / 'connectivity_backup.json'
        
        # Create data directory
        self.DATA_DIR.mkdir(exist_ok=True)
    
    def _get_default_location(self):
        """Generate default location based on computer name"""
        try:
            hostname = socket.gethostname()
            return f"{hostname.lower().replace(' ', '_').replace('-', '_')}"
        except:
            return "unknown_location"
    
    def validate_config(self):
        """Validate configuration and prompt for missing required values"""
        config_valid = True
        
        # Check for required spreadsheet ID
        if not self.GOOGLE_SPREADSHEET_ID:
            print("\n❌ Google Spreadsheet ID is required!")
            print("Please edit the script and set GOOGLE_SPREADSHEET_ID at the top of the file.")
            print("\nTo get your Spreadsheet ID:")
            print("1. Open your Google Spreadsheet")
            print("2. Copy the ID from the URL (the long string between /d/ and /edit)")
            print("   Example: https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit")
            print("   ID: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
            config_valid = False
        
        # Validate timeouts
        if self.PING_TIMEOUT <= 0 or self.HTTP_TIMEOUT <= 0 or self.DNS_TIMEOUT <= 0:
            print("\n❌ All timeout values must be greater than 0")
            config_valid = False
        
        # Validate check interval
        if self.CHECK_INTERVAL <= 0:
            print("\n❌ CHECK_INTERVAL must be greater than 0")
            config_valid = False
        
        # Validate targets
        if not self.PING_TARGETS:
            print("\n❌ At least one PING_TARGET is required")
            config_valid = False
            
        if not self.HTTP_TARGETS:
            print("\n❌ At least one HTTP_TARGET is required")
            config_valid = False
            
        if not self.DNS_SERVERS:
            print("\n❌ At least one DNS_SERVER is required")
            config_valid = False
        
        return config_valid
    
    def print_config(self):
        """Print current configuration"""
        print(f"\n📋 Current Configuration:")
        print(f"  Location ID: {self.LOCATION_ID}")
        print(f"  Check Interval: {self.CHECK_INTERVAL} seconds")
        print(f"  Spreadsheet ID: {self.GOOGLE_SPREADSHEET_ID}")
        print(f"  Timeouts: Ping={self.PING_TIMEOUT}s, HTTP={self.HTTP_TIMEOUT}s, DNS={self.DNS_TIMEOUT}s")
        print(f"  Ping Targets: {', '.join(self.PING_TARGETS)}")
        print(f"  HTTP Targets: {', '.join(self.HTTP_TARGETS)}")
        print(f"  DNS Servers: {', '.join(self.DNS_SERVERS)}")
        print(f"  Service Account File: {self.SERVICE_ACCOUNT_FILE}")
        print()

# Setup logging
def setup_logging(config):
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class GoogleSheetsLogger:
    def __init__(self, spreadsheet_id: str, service_account_file: str):
        self.spreadsheet_id = spreadsheet_id
        self.service_account_file = service_account_file
        self.service = None
        self.credentials = None
        self.last_successful_upload = None
        self.failed_uploads = []
        
        self._initialize_credentials()

    def _initialize_credentials(self):
        """Initialize Google Sheets API credentials"""
        try:
            if not Path(self.service_account_file).exists():
                raise FileNotFoundError(f"Service account file not found: {self.service_account_file}")
            
            self.credentials = ServiceAccountCredentials.from_service_account_file(
                self.service_account_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self._build_service()
            print("✓ Google Sheets API initialized successfully")
            
            # Initialize sheets
            self._initialize_sheets()
            
        except Exception as e:
            print(f"✗ Failed to initialize Google Sheets API: {e}")
            raise

    def _build_service(self):
        """Build or rebuild the Google Sheets service"""
        try:
            # Refresh credentials if needed
            if self.credentials.expired:
                self.credentials.refresh(Request())
            
            self.service = build('sheets', 'v4', credentials=self.credentials)
            return True
        except Exception as e:
            print(f"Failed to build Google Sheets service: {e}")
            return False

    def _execute_with_retry(self, operation, max_retries=3, backoff_factor=2):
        """Execute Google Sheets operation with retry logic"""
        for attempt in range(max_retries):
            try:
                # Ensure service is available
                if self.service is None or self.credentials.expired:
                    if not self._build_service():
                        raise Exception("Failed to build Google Sheets service")
                
                # Execute the operation
                result = operation()
                
                # Mark as successful and process any failed uploads
                self.last_successful_upload = datetime.now()
                self._process_failed_uploads()
                
                return result
                
            except HttpError as e:
                if e.resp.status in [401, 403]:  # Authentication or permission errors
                    print(f"Authentication error (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        # Try to rebuild service
                        self._build_service()
                        time.sleep(backoff_factor ** attempt)
                        continue
                elif e.resp.status == 429:  # Rate limit
                    print(f"Rate limit hit (attempt {attempt + 1}), waiting...")
                    if attempt < max_retries - 1:
                        time.sleep((backoff_factor ** attempt) * 5)  # Longer wait for rate limits
                        continue
                else:
                    print(f"HTTP error (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(backoff_factor ** attempt)
                        continue
            except Exception as e:
                print(f"General error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    # Try to rebuild service
                    self._build_service()
                    time.sleep(backoff_factor ** attempt)
                    continue
        
        # All retries failed
        raise Exception(f"Failed to execute operation after {max_retries} attempts")

    def _store_failed_upload(self, operation_type: str, data: Dict):
        """Store failed upload for later retry"""
        failed_upload = {
            'timestamp': datetime.now().isoformat(),
            'operation_type': operation_type,
            'data': data,
            'retry_count': 0
        }
        
        # Limit the number of failed uploads stored to prevent memory issues
        if len(self.failed_uploads) >= 100:
            # Remove oldest failed uploads
            self.failed_uploads = self.failed_uploads[-50:]
            print("Cleaned up old failed uploads to prevent memory issues")
        
        self.failed_uploads.append(failed_upload)
        print(f"Stored failed upload: {operation_type}")

    def _process_failed_uploads(self):
        """Process any failed uploads that are queued"""
        if not self.failed_uploads:
            return
        
        print(f"Processing {len(self.failed_uploads)} failed uploads...")
        successful_uploads = []
        
        for upload in self.failed_uploads[:]:  # Create a copy to iterate over
            try:
                upload['retry_count'] = upload.get('retry_count', 0) + 1
                
                if upload['operation_type'] == 'connectivity_check':
                    self._log_connectivity_check_direct(upload['data'])
                elif upload['operation_type'] == 'outage_start':
                    self._log_outage_start_direct(upload['data'])
                elif upload['operation_type'] == 'outage_end':
                    self._log_outage_end_direct(upload['data'])
                
                successful_uploads.append(upload)
                print(f"✓ Retried upload successful: {upload['operation_type']}")
                
            except Exception as e:
                print(f"✗ Retry failed for {upload['operation_type']}: {e}")
                # Keep failed uploads with retry count < 5
                if upload.get('retry_count', 0) >= 5:
                    print(f"Giving up on upload after 5 retries: {upload['operation_type']}")
                    successful_uploads.append(upload)  # Remove from queue
        
        # Remove successful uploads from failed queue
        for upload in successful_uploads:
            if upload in self.failed_uploads:
                self.failed_uploads.remove(upload)

    def _initialize_sheets(self):
        """Create necessary sheets if they don't exist"""
        try:
            # Get existing sheets
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            existing_sheets = [sheet['properties']['title'] for sheet in sheet_metadata['sheets']]
            
            requests = []
            
            # Define required sheets
            required_sheets = {
                'Connectivity_Checks': [
                    'Timestamp', 'Location_ID', 'Connected', 'Ping_Success', 
                    'HTTP_Success', 'DNS_Success', 'Avg_Ping_MS', 'Notes'
                ],
                'Outages': [
                    'Location_ID', 'Start_Time', 'End_Time', 'Duration_Seconds',
                    'Duration_Minutes', 'Duration_Hours', 'Status'
                ]
            }
            
            # Create missing sheets
            for sheet_name, headers in required_sheets.items():
                if sheet_name not in existing_sheets:
                    requests.append({
                        'addSheet': {
                            'properties': {
                                'title': sheet_name
                            }
                        }
                    })
            
            # Execute sheet creation requests
            if requests:
                body = {'requests': requests}
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=body
                ).execute()
                print(f"✓ Created {len(requests)} new sheets")
            
            # Add headers to new sheets
            for sheet_name, headers in required_sheets.items():
                if sheet_name not in existing_sheets:
                    self._add_headers(sheet_name, headers)
                    
        except Exception as e:
            print(f"Failed to initialize sheets: {e}")

    def _add_headers(self, sheet_name: str, headers: List[str]):
        """Add headers to a sheet"""
        try:
            range_name = f"{sheet_name}!A1:{chr(65 + len(headers) - 1)}1"
            body = {
                'values': [headers]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            # Format headers
            self._format_headers(sheet_name, len(headers))
            
        except Exception as e:
            print(f"Failed to add headers to {sheet_name}: {e}")

    def _format_headers(self, sheet_name: str, num_columns: int):
        """Format header row"""
        try:
            # Get sheet ID
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in sheet_metadata['sheets']:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                return
            
            requests = [
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1,
                            'startColumnIndex': 0,
                            'endColumnIndex': num_columns
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                                'textFormat': {'bold': True}
                            }
                        },
                        'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                    }
                }
            ]
            
            body = {'requests': requests}
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
        except Exception as e:
            print(f"Failed to format headers for {sheet_name}: {e}")

    def log_connectivity_check(self, data: Dict):
        """Log connectivity check to Google Sheets with retry logic"""
        try:
            self._execute_with_retry(lambda: self._log_connectivity_check_direct(data))
        except Exception as e:
            print(f"Failed to log connectivity check after retries: {e}")
            self._store_failed_upload('connectivity_check', data)

    def _log_connectivity_check_direct(self, data: Dict):
        """Direct connectivity check logging (internal method)"""
        # Calculate summary metrics
        ping_success = any(result.get('success', False) for result in data.get('ping_results', []))
        http_success = any(result.get('success', False) for result in data.get('http_results', []))
        dns_success = any(result.get('success', False) for result in data.get('dns_results', []))
        
        # Calculate average ping - handle None values properly
        ping_times = []
        for r in data.get('ping_results', []):
            if r.get('success', False) and r.get('latency_ms') is not None:
                try:
                    ping_times.append(float(r['latency_ms']))
                except (ValueError, TypeError):
                    pass  # Skip invalid values
        
        avg_ping = round(sum(ping_times) / len(ping_times), 2) if ping_times else 0
        
        # Prepare row data
        row_data = [
            data.get('timestamp', ''),
            data.get('location_id', ''),
            'TRUE' if data.get('connected', False) else 'FALSE',
            'TRUE' if ping_success else 'FALSE',
            'TRUE' if http_success else 'FALSE',
            'TRUE' if dns_success else 'FALSE',
            avg_ping,
            self._generate_notes(data)
        ]
        
        return self._append_row('Connectivity_Checks', row_data)

    def log_outage_start(self, location_id: str, start_time: str):
        """Log start of an outage with retry logic"""
        try:
            data = {'location_id': location_id, 'start_time': start_time}
            self._execute_with_retry(lambda: self._log_outage_start_direct(data))
        except Exception as e:
            print(f"Failed to log outage start after retries: {e}")
            self._store_failed_upload('outage_start', data)

    def _log_outage_start_direct(self, data: Dict):
        """Direct outage start logging (internal method)"""
        row_data = [
            data['location_id'],
            data['start_time'],
            '',  # End time (empty for ongoing)
            '',  # Duration seconds (empty for ongoing)
            '',  # Duration minutes (empty for ongoing)
            '',  # Duration hours (empty for ongoing)
            'ONGOING'
        ]
        
        return self._append_row('Outages', row_data)

    def log_outage_end(self, location_id: str, start_time: str, end_time: str, duration_seconds: float):
        """Update outage record when it ends with retry logic"""
        try:
            data = {
                'location_id': location_id,
                'start_time': start_time,
                'end_time': end_time,
                'duration_seconds': duration_seconds
            }
            self._execute_with_retry(lambda: self._log_outage_end_direct(data))
        except Exception as e:
            print(f"Failed to log outage end after retries: {e}")
            self._store_failed_upload('outage_end', data)

    def _log_outage_end_direct(self, data: Dict):
        """Direct outage end logging (internal method)"""
        # Find the ongoing outage row
        range_name = 'Outages!A:G'
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        # Find the row with matching location and ongoing status
        for i, row in enumerate(values):
            if (len(row) >= 7 and 
                row[0] == data['location_id'] and 
                row[1] == data['start_time'] and 
                row[6] == 'ONGOING'):
                
                # Update the row
                duration_minutes = round(data['duration_seconds'] / 60, 2)
                duration_hours = round(data['duration_seconds'] / 3600, 2)
                
                update_range = f'Outages!C{i+1}:G{i+1}'
                update_data = [
                    data['end_time'],
                    data['duration_seconds'],
                    duration_minutes,
                    duration_hours,
                    'RESOLVED'
                ]
                
                body = {'values': [update_data]}
                result = self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=update_range,
                    valueInputOption='RAW',
                    body=body
                ).execute()
                
                print(f"✓ Updated outage record for {data['location_id']}")
                return result
        
        # If no ongoing outage found, create a new complete record
        print(f"No ongoing outage found, creating complete outage record")
        duration_minutes = round(data['duration_seconds'] / 60, 2)
        duration_hours = round(data['duration_seconds'] / 3600, 2)
        
        row_data = [
            data['location_id'],
            data['start_time'],
            data['end_time'],
            data['duration_seconds'],
            duration_minutes,
            duration_hours,
            'RESOLVED'
        ]
        
        return self._append_row('Outages', row_data)

    def _append_row(self, sheet_name: str, row_data: List[Any]):
        """Append a row to a sheet with better error handling"""
        range_name = f"{sheet_name}!A:Z"
        body = {
            'values': [row_data]
        }
        
        result = self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        return result

    def recover_from_backup(self, backup_data: List[Dict]):
        """Recover and upload data from local backup after connectivity issues"""
        if not backup_data:
            return {'connectivity_checks': 0, 'outages_started': 0, 'outages_completed': 0, 'errors': 0}
            
        print(f"Starting recovery process with {len(backup_data)} records...")
        
        recovery_stats = {
            'connectivity_checks': 0,
            'outages_started': 0,
            'outages_completed': 0,
            'errors': 0
        }
        
        # Sort backup data by timestamp
        sorted_data = sorted(backup_data, key=lambda x: x.get('timestamp', ''))
        
        # Track outages for proper completion
        ongoing_outages = {}
        
        for record in sorted_data:
            try:
                # Skip if already uploaded (check timestamp against last successful upload)
                if (self.last_successful_upload and 
                    record.get('timestamp') and 
                    record['timestamp'] < self.last_successful_upload.isoformat()):
                    continue
                
                # Upload connectivity check
                if record.get('connected') is not None:
                    self._execute_with_retry(lambda: self._log_connectivity_check_direct(record), max_retries=2)
                    recovery_stats['connectivity_checks'] += 1
                
                # Handle status changes (outages)
                if 'status_change' in record:
                    status_change = record['status_change']
                    
                    if status_change['type'] == 'outage_start':
                        data = {
                            'location_id': status_change['location_id'],
                            'start_time': status_change['timestamp']
                        }
                        self._execute_with_retry(lambda: self._log_outage_start_direct(data), max_retries=2)
                        ongoing_outages[status_change['location_id']] = status_change['timestamp']
                        recovery_stats['outages_started'] += 1
                        
                    elif status_change['type'] == 'outage_end':
                        data = {
                            'location_id': status_change['location_id'],
                            'start_time': status_change['outage_start'],
                            'end_time': status_change['timestamp'],
                            'duration_seconds': status_change['duration_seconds']
                        }
                        self._execute_with_retry(lambda: self._log_outage_end_direct(data), max_retries=2)
                        if status_change['location_id'] in ongoing_outages:
                            del ongoing_outages[status_change['location_id']]
                        recovery_stats['outages_completed'] += 1
                
                # Small delay to avoid rate limits
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error recovering record {record.get('timestamp', 'unknown')}: {e}")
                recovery_stats['errors'] += 1
        
        print(f"Recovery completed:")
        print(f"  ✓ Connectivity checks: {recovery_stats['connectivity_checks']}")
        print(f"  ✓ Outages started: {recovery_stats['outages_started']}")
        print(f"  ✓ Outages completed: {recovery_stats['outages_completed']}")
        print(f"  ✗ Errors: {recovery_stats['errors']}")
        
        if ongoing_outages:
            print(f"  ⚠ Ongoing outages still active: {list(ongoing_outages.keys())}")
        
        return recovery_stats

    def _generate_notes(self, data: Dict) -> str:
        """Generate notes field with failure details"""
        notes = []
        
        # Check for ping failures
        ping_failures = []
        for r in data.get('ping_results', []):
            if not r.get('success', False):
                ping_failures.append(r.get('target', 'unknown'))
        
        if ping_failures:
            notes.append(f"Ping failed: {', '.join(ping_failures)}")
        
        # Check for HTTP failures
        http_failures = []
        for r in data.get('http_results', []):
            if not r.get('success', False):
                http_failures.append(r.get('url', 'unknown'))
        
        if http_failures:
            notes.append(f"HTTP failed: {', '.join(http_failures)}")
        
        # Check for DNS failures
        dns_failures = []
        for r in data.get('dns_results', []):
            if not r.get('success', False):
                dns_failures.append(r.get('server', 'unknown'))
        
        if dns_failures:
            notes.append(f"DNS failed: {', '.join(dns_failures)}")
        
        return '; '.join(notes) if notes else 'All tests passed'

class InternetMonitor:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.last_status = None
        self.outage_start_time = None
        self.connectivity_restored_recently = False
        self.last_backup_recovery = None
        
        # Initialize Google Sheets logger
        if self.config.GOOGLE_SPREADSHEET_ID and Path(self.config.SERVICE_ACCOUNT_FILE).exists():
            try:
                self.sheets_logger = GoogleSheetsLogger(
                    self.config.GOOGLE_SPREADSHEET_ID, 
                    self.config.SERVICE_ACCOUNT_FILE
                )
                self.logger.info("Google Sheets integration enabled")
            except Exception as e:
                self.logger.error(f"Failed to initialize Google Sheets: {e}")
                self.sheets_logger = None
        else:
            self.logger.warning("Google Sheets not configured - data will only be stored locally")
            self.sheets_logger = None

    def ping_test(self, target: str, timeout: int = None) -> Dict:
        """Test connectivity using ping"""
        if timeout is None:
            timeout = self.config.PING_TIMEOUT
            
        try:
            system = platform.system().lower()
            if system == "windows":
                cmd = ['ping', '-n', '1', '-w', str(timeout * 1000), target]
            else:
                cmd = ['ping', '-c', '1', '-W', str(timeout), target]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 2  # Add 2 seconds buffer for subprocess timeout
            )
            
            if result.returncode == 0:
                # Extract latency from ping output
                output = result.stdout.lower()
                latency = None
                
                try:
                    # Try different parsing approaches for different OS formats
                    if 'time=' in output:
                        # Linux/Windows format: time=X.XXXms
                        time_part = output.split('time=')[1].split()[0]
                        time_part = time_part.replace('ms', '').replace('<', '')
                        latency = float(time_part)
                    elif 'round-trip' in output and '=' in output:
                        # macOS format: round-trip min/avg/max/stddev = X.XXX/Y.YYY/Z.ZZZ/W.WWW ms
                        rtt_match = re.search(r'round-trip.*?=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)', output)
                        if rtt_match:
                            # Use the average (second value)
                            latency = float(rtt_match.group(2))
                    elif system == "windows" and 'ms' in output:
                        # Windows alternative format
                        ms_match = re.search(r'time[<>=]*\s*([0-9.]+)ms', output)
                        if ms_match:
                            latency = float(ms_match.group(1))
                except:
                    pass  # Fallback to None if parsing fails
                
                return {'success': True, 'latency_ms': latency, 'target': target, 'timeout_used': timeout}
            else:
                return {'success': False, 'error': result.stderr.strip() or 'Ping failed', 'target': target, 'timeout_used': timeout}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f'Ping timeout after {timeout} seconds', 'target': target, 'timeout_used': timeout}
        except Exception as e:
            return {'success': False, 'error': str(e), 'target': target, 'timeout_used': timeout}

    def http_test(self, url: str, timeout: int = None) -> Dict:
        """Test HTTP connectivity"""
        if timeout is None:
            timeout = self.config.HTTP_TIMEOUT
            
        try:
            start_time = time.time()
            
            # Use urllib for simpler dependency management
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Internet-Monitor/1.0')
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                response_time = (time.time() - start_time) * 1000
                
                return {
                    'success': response.status == 200,
                    'status_code': response.status,
                    'response_time_ms': response_time,
                    'url': url,
                    'timeout_used': timeout
                }
                
        except urllib.error.HTTPError as e:
            return {'success': False, 'error': f'HTTP {e.code}: {e.reason}', 'url': url, 'timeout_used': timeout}
        except urllib.error.URLError as e:
            return {'success': False, 'error': f'URL error: {e.reason}', 'url': url, 'timeout_used': timeout}
        except socket.timeout:
            return {'success': False, 'error': f'HTTP timeout after {timeout} seconds', 'url': url, 'timeout_used': timeout}
        except Exception as e:
            return {'success': False, 'error': str(e), 'url': url, 'timeout_used': timeout}

    def dns_test(self, server: str, domain: str = 'google.com', timeout: int = None) -> Dict:
        """Test DNS resolution"""
        if timeout is None:
            timeout = self.config.DNS_TIMEOUT
            
        try:
            import dns.resolver
            
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [server]
            resolver.timeout = timeout
            resolver.lifetime = timeout
            
            start_time = time.time()
            answers = resolver.resolve(domain, 'A')
            response_time = (time.time() - start_time) * 1000
            
            return {
                'success': True,
                'response_time_ms': response_time,
                'server': server,
                'resolved_ips': [str(rdata) for rdata in answers],
                'timeout_used': timeout
            }
        except dns.resolver.Timeout:
            return {'success': False, 'error': f'DNS timeout after {timeout} seconds', 'server': server, 'timeout_used': timeout}
        except dns.resolver.NXDOMAIN:
            return {'success': False, 'error': f'Domain {domain} not found', 'server': server, 'timeout_used': timeout}
        except Exception as e:
            return {'success': False, 'error': str(e), 'server': server, 'timeout_used': timeout}

    def comprehensive_check(self) -> Dict:
        """Perform comprehensive connectivity check"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Ping tests
        ping_results = []
        for target in self.config.PING_TARGETS:
            try:
                result = self.ping_test(target)
                ping_results.append(result)
            except Exception as e:
                ping_results.append({
                    'success': False, 
                    'error': str(e), 
                    'target': target, 
                    'timeout_used': self.config.PING_TIMEOUT
                })
        
        # HTTP tests
        http_results = []
        for url in self.config.HTTP_TARGETS:
            try:
                result = self.http_test(url)
                http_results.append(result)
            except Exception as e:
                http_results.append({
                    'success': False, 
                    'error': str(e), 
                    'url': url, 
                    'timeout_used': self.config.HTTP_TIMEOUT
                })
        
        # DNS tests
        dns_results = []
        for server in self.config.DNS_SERVERS:
            try:
                result = self.dns_test(server)
                dns_results.append(result)
            except Exception as e:
                dns_results.append({
                    'success': False, 
                    'error': str(e), 
                    'server': server, 
                    'timeout_used': self.config.DNS_TIMEOUT
                })
        
        # Determine overall connectivity
        ping_success = any(result.get('success', False) for result in ping_results)
        http_success = any(result.get('success', False) for result in http_results)
        dns_success = any(result.get('success', False) for result in dns_results)
        
        overall_connected = ping_success and (http_success or dns_success)
        
        check_result = {
            'timestamp': timestamp,
            'location_id': self.config.LOCATION_ID,
            'connected': overall_connected,
            'ping_results': ping_results,
            'http_results': http_results,
            'dns_results': dns_results
        }
        
        return check_result

    def detect_status_change(self, current_status: bool, timestamp: str) -> Optional[Dict]:
        """Detect connectivity status changes and track outages"""
        if self.last_status is None:
            self.last_status = current_status
            return None
        
        status_change = None
        
        if self.last_status and not current_status:
            # Connection lost
            self.outage_start_time = timestamp
            self.connectivity_restored_recently = False
            status_change = {
                'type': 'outage_start',
                'timestamp': timestamp,
                'location_id': self.config.LOCATION_ID
            }
            self.logger.warning(f"Internet outage detected at {self.config.LOCATION_ID}")
            
            # Log to Google Sheets (will be stored locally if no connection)
            if self.sheets_logger:
                self.sheets_logger.log_outage_start(self.config.LOCATION_ID, timestamp)
            
        elif not self.last_status and current_status:
            # Connection restored
            self.connectivity_restored_recently = True
            
            if self.outage_start_time:
                start_dt = datetime.fromisoformat(self.outage_start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                duration = (end_dt - start_dt).total_seconds()
                
                status_change = {
                    'type': 'outage_end',
                    'timestamp': timestamp,
                    'location_id': self.config.LOCATION_ID,
                    'outage_start': self.outage_start_time,
                    'duration_seconds': duration
                }
                
                duration_min = duration / 60
                self.logger.info(f"Internet restored at {self.config.LOCATION_ID}. Outage duration: {duration_min:.1f} minutes")
                
                # Log to Google Sheets (should work now that connection is restored)
                if self.sheets_logger:
                    self.sheets_logger.log_outage_end(
                        self.config.LOCATION_ID, 
                        self.outage_start_time, 
                        timestamp, 
                        duration
                    )
                
                self.outage_start_time = None
        
        self.last_status = current_status
        return status_change

    def attempt_backup_recovery(self):
        """Attempt to recover and upload data from local backup"""
        if not self.sheets_logger:
            return
        
        try:
            # Only attempt recovery if connectivity was recently restored
            # and we haven't done a recovery recently
            now = datetime.now()
            if (self.connectivity_restored_recently and 
                (self.last_backup_recovery is None or 
                 (now - self.last_backup_recovery).total_seconds() > 300)):  # 5 minutes
                
                if self.config.BACKUP_FILE.exists():
                    self.logger.info("Attempting to recover data from local backup...")
                    
                    try:
                        with open(self.config.BACKUP_FILE, 'r') as f:
                            backup_data = json.load(f)
                    except json.JSONDecodeError:
                        self.logger.error("Backup file is corrupted, skipping recovery")
                        return
                    except Exception as e:
                        self.logger.error(f"Error reading backup file: {e}")
                        return
                    
                    if backup_data:
                        recovery_stats = self.sheets_logger.recover_from_backup(backup_data)
                        self.logger.info(f"Backup recovery completed: {recovery_stats}")
                        self.last_backup_recovery = now
                        self.connectivity_restored_recently = False
                
        except Exception as e:
            self.logger.error(f"Error during backup recovery: {e}")

    def save_local_backup(self, data: Dict):
        """Save data locally as backup"""
        try:
            # Load existing data
            local_data = []
            if self.config.BACKUP_FILE.exists():
                with open(self.config.BACKUP_FILE, 'r') as f:
                    local_data = json.load(f)
            
            # Add new data
            local_data.append(data)
            
            # Keep only last 1000 entries to prevent excessive disk usage
            if len(local_data) > 1000:
                local_data = local_data[-1000:]
            
            # Save back to file
            with open(self.config.BACKUP_FILE, 'w') as f:
                json.dump(local_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save local backup: {e}")

    def run_check(self):
        """Run a single connectivity check"""
        try:
            # Perform comprehensive check
            result = self.comprehensive_check()
            
            # Detect status changes
            status_change = self.detect_status_change(result['connected'], result['timestamp'])
            if status_change:
                result['status_change'] = status_change
            
            # Save local backup (always works)
            self.save_local_backup(result)
            
            # Log to Google Sheets (with retry logic)
            if self.sheets_logger:
                self.sheets_logger.log_connectivity_check(result)
            
            # Attempt backup recovery if connectivity was recently restored
            if self.connectivity_restored_recently:
                self.attempt_backup_recovery()
            
            status = "CONNECTED" if result['connected'] else "DISCONNECTED"
            self.logger.info(f"Check completed - Status: {status}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error during connectivity check: {e}")
            return None

    def run_continuous(self):
        """Run continuous monitoring"""
        self.logger.info(f"Starting Internet Monitor for location: {self.config.LOCATION_ID}")
        self.logger.info(f"Check interval: {self.config.CHECK_INTERVAL} seconds")
        
        # Run initial check
        self.run_check()
        
        try:
            while True:
                time.sleep(self.config.CHECK_INTERVAL)
                self.run_check()
                
                # Periodic attempt to process any failed uploads (every 10 checks)
                if hasattr(self, 'check_count'):
                    self.check_count += 1
                else:
                    self.check_count = 1
                
                if self.check_count % 10 == 0 and self.sheets_logger:
                    if self.sheets_logger.failed_uploads:
                        self.logger.info(f"Attempting to process {len(self.sheets_logger.failed_uploads)} failed uploads...")
                        self.sheets_logger._process_failed_uploads()
                
        except KeyboardInterrupt:
            self.logger.info("Monitor stopped by user")
            
            # Final attempt to upload any pending data
            if self.sheets_logger and self.sheets_logger.failed_uploads:
                self.logger.info("Final attempt to upload pending data...")
                self.sheets_logger._process_failed_uploads()
                
        except Exception as e:
            self.logger.error(f"Monitor stopped due to error: {e}")
            raise

def main():
    """Main function"""
    print("Internet Connectivity Monitor")
    print("=" * 40)
    
    # Initialize configuration
    config = Config()
    
    # Print current configuration
    config.print_config()
    
    # Validate configuration
    if not config.validate_config():
        print("\n❌ Configuration errors found. Please edit the script and fix the issues above.")
        sys.exit(1)
    
    # Check for required files
    if not Path(config.SERVICE_ACCOUNT_FILE).exists():
        print(f"\n❌ Service account file not found: {config.SERVICE_ACCOUNT_FILE}")
        print("\nPlease follow these steps:")
        print("1. Create a Google Cloud service account")
        print("2. Download the JSON key file")
        print("3. Save it as 'service_account.json' in the same directory as this script")
        print("4. Share your Google Spreadsheet with the service account email")
        print("\nSee the setup guide for detailed instructions.")
        sys.exit(1)
    
    # Setup logging
    logger = setup_logging(config)
    
    # Initialize monitor
    monitor = InternetMonitor(config, logger)
    
    # Test connection to Google Sheets
    if monitor.sheets_logger is None:
        print("❌ Google Sheets integration failed")
        print("Data will only be saved locally")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            sys.exit(1)
    
    print(f"\n✅ Monitor configured for location: {config.LOCATION_ID}")
    print(f"✅ Data will be logged every {config.CHECK_INTERVAL} seconds")
    print(f"✅ Timeouts: Ping={config.PING_TIMEOUT}s, HTTP={config.HTTP_TIMEOUT}s, DNS={config.DNS_TIMEOUT}s")
    if monitor.sheets_logger:
        print(f"✅ Google Sheets integration active")
        print(f"✅ Spreadsheet: https://docs.google.com/spreadsheets/d/{config.GOOGLE_SPREADSHEET_ID}")
    
    print(f"✅ Local backup: {config.BACKUP_FILE}")
    print(f"✅ Log file: {config.LOG_FILE}")
    
    print("\n🚀 Starting monitoring... (Press Ctrl+C to stop)")
    
    # Run continuous monitoring
    monitor.run_continuous()

if __name__ == "__main__":
    main()
