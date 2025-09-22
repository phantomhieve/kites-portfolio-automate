#!/usr/bin/env python3
"""
Demo script to test the webhook-based token renewal system.

This script demonstrates how the automated token renewal works:
1. Starts a webhook server on localhost:8080
2. Shows login URLs for each profile
3. Waits for OAuth callbacks to capture request tokens
4. Automatically generates access tokens

Usage:
    python test_webhook_demo.py
"""

import os
import sys
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, 'src')

from kites_automate.auth.webhook_server import TokenWebhookServer
from kites_automate.auth.automated_auth import AutomatedKiteAuth


def test_single_profile():
    """Test automated renewal for a single profile."""
    print("🧪 Testing Automated Token Renewal Demo")
    print("=" * 50)
    
      # Use account1 credentials for testing
    api_key = "REDACTED_API_KEY"    # API key
    api_secret = "REDACTED_API_SECRET"    # API secret
    profile_name = "HUF_demo"
    
    print(f"📋 Profile: {profile_name}")
    print(f"🔑 API Key: {api_key}")
    print()
    
    # Create auth manager
    auth = AutomatedKiteAuth(api_key, api_secret, profile_name)
    
    # Start webhook server
    server = TokenWebhookServer(host="localhost", port=8080)
    
    try:
        print("🚀 Starting webhook server...")
        callback_url = server.start()
        print(f"✅ Webhook server running: {callback_url}")
        print()
        
        # Generate login URL
        login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3&redirect_url={callback_url}"
        
        print("🔗 AUTOMATED TOKEN RENEWAL PROCESS:")
        print("1. Open this URL in your browser:")
        print(f"   {login_url}")
        print()
        print("2. Login with your Zerodha credentials")
        print("3. Complete 2FA if prompted")
        print("4. The system will automatically capture the token!")
        print()
        print("⏳ Waiting for OAuth callback (5 minutes timeout)...")
        
        # Wait for token capture
        token_data = server.wait_for_token(timeout=300)
        
        if token_data and token_data.get('request_token'):
            request_token = token_data['request_token']
            print(f"✅ Request token captured: {request_token[:10]}...")
            
            # Test access token generation
            print("🔄 Generating access token...")
            access_token = auth._generate_access_token(request_token)
            
            if access_token:
                print(f"✅ Access token generated: {access_token[:10]}...")
                print("✅ AUTOMATED RENEWAL SUCCESSFUL! 🎉")
                
                # Save token
                token_data = {
                    "access_token": access_token,
                    "refresh_token": "",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now().replace(hour=23, minute=59, second=59)).isoformat()
                }
                auth._save_token(token_data)
                print(f"💾 Token saved to: {auth.token_file}")
                
            else:
                print("❌ Failed to generate access token")
        else:
            print("❌ Failed to capture request token")
            print("💡 Make sure you completed the login process in the browser")
            
    except KeyboardInterrupt:
        print("\n⚠️ Demo interrupted by user")
    except Exception as exc:
        print(f"❌ Demo failed: {exc}")
    finally:
        server.stop()
        print("🛑 Webhook server stopped")


if __name__ == "__main__":
    test_single_profile()
