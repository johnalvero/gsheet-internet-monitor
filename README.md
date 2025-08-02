# Google Sheet Internet Connectivity Monitor
Monitors internet connectivity via PING, DNS and Web -- sends reports to Google Sheet

## Google Sheets API Setup Guide

This guide walks you through setting up Google Sheets integration for the Internet Connectivity Monitor, from enabling APIs to configuring service account authentication.

## Overview

By the end of this guide, you'll have:
- ✅ Google Sheets API enabled in Google Cloud Console
- ✅ Service account created with proper permissions
- ✅ JSON credentials file downloaded and configured
- ✅ Google Spreadsheet created and shared with the service account
- ✅ Internet Monitor configured to log data to your spreadsheet

**Estimated time**: 15-20 minutes  
**Prerequisites**: Google account with access to Google Cloud Console

---

## Step 1: Google Cloud Console Setup

### 1.1 Access Google Cloud Console
1. Navigate to [Google Cloud Console]()
2. Sign in with your Google account

### 1.2 Create or Select Project
1. **New Project**: Click the project dropdown → "New Project"
   - Enter project name (e.g., "Internet Monitor")
   - Click "Create"
2. **Existing Project**: Select from the project dropdown

### 1.3 Enable Required APIs
1. Navigate to **APIs & Services** → **Library**
2. Search for and enable these APIs:
   - **Google Sheets API**
     - Click "Google Sheets API"
     - Click "Enable"
---

## Step 2: Create Service Account

### 2.1 Navigate to Service Accounts
1. Go to **IAM & Admin** → **Service Accounts**
2. Click **"+ Create Service Account"**

### 2.2 Configure Service Account
1. **Service account details**:
   - **Service account name**: `internet-monitor-service`
   - **Service account ID**: (auto-generated, e.g., `internet-monitor-service@your-project.iam.gserviceaccount.com`)
   - **Description**: `Service account for Internet Connectivity Monitor data logging`
2. Click **"Create and Continue"**

### 2.3 Skip Role Assignment
1. **Grant access to project** (Step 2): Click **"Continue"** (skip this step)
2. **Grant users access** (Step 3): Click **"Done"**

> 💡 **Note**: No project-level roles needed since we'll grant access directly to the spreadsheet.

---

## Step 3: Generate Service Account Key

### 3.1 Access Service Account
1. From the Service Accounts list, click on your newly created service account
2. Navigate to the **"Keys"** tab

### 3.2 Create JSON Key
1. Click **"Add Key"** → **"Create new key"**
2. Select **"JSON"** format
3. Click **"Create"**
4. The JSON file will automatically download

### 3.3 Secure the Key File
1. **Rename** the downloaded file to `service_account.json`
2. **Move** it to your Internet Monitor directory (same folder as `internet-monitor.py`)
3. **Set permissions** (Unix/Linux/macOS):
   ```bash
   chmod 600 service_account.json
   ```

> 🔒 **Security**: Treat this file like a password. Never commit it to version control or share it publicly.

---

## Step 4: Create Google Spreadsheet

### 4.1 Create New Spreadsheet
1. Go to [Google Sheets](https://sheets.google.com)
2. Click **"+ Blank"** to create a new spreadsheet
3. **Rename** it (e.g., "Internet Monitor")

### 4.2 Extract Spreadsheet ID
1. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/lnasdfGHASDWefasdljeofmsdglo/edit
                                      ↑                                    ↑
                                      └─── This is your Spreadsheet ID ───┘
   ```
2. **Save this ID** - you'll need it for configuration

> 📝 **Example**: If your URL is `https://docs.google.com/spreadsheets/d/lnasdfGHASDWefasdljeofmsdglo/edit`, then your Spreadsheet ID is `lnasdfGHASDWefasdljeofmsdglo`

---

## Step 5: Share Spreadsheet with Service Account

### 5.1 Find Service Account Email
1. Open your `service_account.json` file
2. Look for the `"client_email"` field:
   ```json
   {
     "type": "service_account",
     "project_id": "your-project-123456",
     "client_email": "internet-monitor-service@your-project.iam.gserviceaccount.com",
     ...
   }
   ```
3. **Copy** the email address

### 5.2 Share the Spreadsheet
1. In your Google Spreadsheet, click **"Share"** (top-right corner)
2. **Add the service account email**:
   - Paste the service account email in the "Add people and groups" field
   - Set permission to **"Editor"**
   - **Uncheck** "Notify people" (service accounts don't need notifications)
3. Click **"Send"**

### 5.3 Verify Sharing
You should see the service account email listed in the sharing permissions with "Editor" access.

---

## Step 6: Configure Internet Monitor

### 6.1 Update Configuration
1. Open `internet-monitor.py`
2. Find the configuration section (around line 27):
   ```python
   GOOGLE_SPREADSHEET_ID = "lnasdfGHASDWefasdljeofmsdglo"  # Replace with your ID
   ```
3. **Replace** with your actual Spreadsheet ID

### 6.2 Verify File Placement
Ensure your directory structure looks like this:
```
internet_monitor/
├── internet-monitor.py
├── service_account.json          ← Must be here
└── monitor_data/                  ← Will be created automatically
    ├── connectivity_backup.json
    └── monitor.log
```

### 6.3 Test the Setup
1. Run the monitor:
   ```bash
   python internet-monitor.py
   ```
2. Look for these success messages:
   ```
   ✓ Google Sheets API initialized successfully
   ✓ Created 2 new sheets
   ✓ Google Sheets integration active
   ```

---

## Troubleshooting

### Common Error Messages

#### ❌ "Service account file not found"
```
FileNotFoundError: Service account file not found: service_account.json
```
**Solution**: Ensure `service_account.json` is in the same directory as the Python script.

#### ❌ "Failed to initialize Google Sheets API: 403 Forbidden"
```
google.auth.exceptions.RefreshError: The credentials do not contain the necessary fields
```
**Solutions**:
1. Verify both Google Sheets API and Google Drive API are enabled
2. Regenerate the service account key if it's corrupted
3. Check the JSON file is valid (proper formatting)

#### ❌ "The caller does not have permission"
```
HttpError 403: The caller does not have permission to access the spreadsheet
```
**Solutions**:
1. Verify the spreadsheet is shared with the correct service account email
2. Ensure the service account has "Editor" permissions
3. Double-check the Spreadsheet ID in your configuration

#### ❌ "Spreadsheet not found"
```
HttpError 404: Requested entity was not found
```
**Solutions**:
1. Verify the Spreadsheet ID is correct
2. Ensure the spreadsheet exists and is accessible
3. Check that the service account has been granted access

### API Quota Issues

If you see quota-related errors:
1. Go to **APIs & Services** → **Quotas** in Google Cloud Console
2. Check your Google Sheets API usage
3. Request quota increases if needed (usually not required for personal use)

### Authentication Refresh Issues

If you see authentication errors after some time:
1. The service account key might be expired or revoked
2. Regenerate the key following Step 3
3. Replace the old `service_account.json` file

---

## Security Best Practices

### 🔐 Service Account Key Security
- **Never** commit `service_account.json` to version control
- **Restrict** file permissions: `chmod 600 service_account.json`
- **Store** in a secure location
- **Rotate** keys periodically (every 90-365 days)

### 📊 Spreadsheet Access Control
- **Limit** sharing to necessary service accounts only
- **Review** sharing permissions regularly
- **Use** "Editor" permission (not "Owner") for service accounts
- **Monitor** unusual API activity in Google Cloud Console

### 🔍 Monitoring
- **Check** Google Cloud Console for API usage patterns
- **Set up** billing alerts to monitor unexpected usage
- **Review** audit logs for suspicious access

---

## Next Steps

Once setup is complete:

1. **Test thoroughly**: Run the monitor for a few minutes to ensure data appears in your spreadsheet
2. **Configure location**: Update `LOCATION_ID` for multiple monitoring locations
3. **Adjust settings**: Modify check intervals and timeouts based on your needs
4. **Set up monitoring**: Consider running the monitor as a service for continuous operation

### Generated Spreadsheet Structure

The monitor will automatically create two sheets:

#### 📋 Connectivity_Checks
| Column | Description |
|--------|-------------|
| Timestamp | ISO format timestamp of the check |
| Location_ID | Your configured location identifier |
| Connected | TRUE/FALSE overall connectivity status |
| Ping_Success | TRUE/FALSE ping test results |
| HTTP_Success | TRUE/FALSE HTTP test results |
| DNS_Success | TRUE/FALSE DNS test results |
| Avg_Ping_MS | Average ping latency in milliseconds |
| Notes | Details about failed tests |

#### 📊 Outages
| Column | Description |
|--------|-------------|
| Location_ID | Your configured location identifier |
| Start_Time | When the outage began |
| End_Time | When connectivity was restored |
| Duration_Seconds | Outage duration in seconds |
| Duration_Minutes | Outage duration in minutes |
| Duration_Hours | Outage duration in hours |
| Status | ONGOING or RESOLVED |

---

## Support

If you encounter issues not covered in this guide:

1. **Check logs**: Review `monitor_data/monitor.log` for detailed error messages
2. **Verify configuration**: Ensure all settings in the configuration section are correct
3. **Test individually**: Try accessing the Google Sheets API manually to isolate issues
4. **Google Cloud Support**: For API-specific issues, consult Google Cloud documentation

---
