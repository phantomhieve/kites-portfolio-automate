"""
Kites Portfolio Tracker

Main script to fetch and update portfolio data from Zerodha Kite
to Google Sheets with intelligent quota management.
"""

import os
import time
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

from kites import KiteAuthManager, PortfolioManager, SheetManager
from kites.sheets import SummaryManager


def load_profiles_config() -> Dict[str, Any]:
    """Load profiles configuration from JSON file."""
    config_file = "profiles.json"
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file '{config_file}' not found!")
        print("📋 Please copy 'profiles.json.example' to 'profiles.json' and configure your profiles.")
        print("\n💡 Quick setup:")
        print(f"   cp profiles.json.example {config_file}")
        print(f"   # Edit {config_file} with your profile details")
        raise FileNotFoundError(f"Configuration file '{config_file}' not found")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        if 'profiles' not in config or not config['profiles']:
            raise ValueError("No profiles found in configuration")
            
        return config
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in '{config_file}': {e}")
        raise
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        raise


def get_profiles() -> List[Dict[str, Any]]:
    """Get profile configurations from JSON file."""
    try:
        config = load_profiles_config()
        profiles = []
        
        for profile_config in config['profiles']:
            # Get API credentials from environment variables
            api_key = os.getenv(profile_config['api_key_env'])
            api_secret = os.getenv(profile_config['api_secret_env'])
            
            if not api_key or not api_secret:
                print(f"⚠️ Warning: Missing credentials for profile '{profile_config['profile_name']}'")
                print(f"   Please set environment variables: {profile_config['api_key_env']}, {profile_config['api_secret_env']}")
                continue
            
            profiles.append({
                "api_key": api_key,
                "api_secret": api_secret,
                "token_file": profile_config['token_file'],
                "profile_name": profile_config['profile_name'],
                "description": profile_config.get('description', ''),
                "exception_list": profile_config.get('exception_list', [])
            })
        
        if not profiles:
            print("❌ No valid profiles found! Please check your configuration and environment variables.")
            raise ValueError("No valid profiles configured")
            
        return profiles
        
    except Exception as e:
        print(f"❌ Failed to load profiles: {e}")
        raise


def get_spreadsheet_name() -> str:
    """Get spreadsheet name from configuration."""
    try:
        config = load_profiles_config()
        return config.get('settings', {}).get('spreadsheet_name', 'Portfolio')
    except:
        return 'Portfolio'  # Default fallback


def get_summary_sheet_name() -> str:
    """Get summary sheet name from configuration."""
    try:
        config = load_profiles_config()
        return config.get('settings', {}).get('summary_sheet_name', 'Summary')
    except:
        return 'Summary'  # Default fallback


def smart_update():
    """Smart update with local state tracking - only formats when needed."""
    print("🧠 Smart Update Mode")
    print("=" * 50)
    print("📊 Updates data + applies formatting only when necessary")
    print("🎨 Uses local state tracking (no API calls for checks)")
    print()
    
    # Initialize managers
    sheet_manager = SheetManager("credentials.json")
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)
    
    # Get spreadsheet
    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    
    # Process each profile
    portfolio_summaries = {}
    
    for profile in get_profiles():
        print(f"\n📊 Processing {profile['profile_name']}'s portfolio...")
        if profile.get('description'):
            print(f"   📝 {profile['description']}")
        
        try:
            # Authenticate with Kite
            kite_auth = KiteAuthManager(
                profile["api_key"],
                profile["api_secret"],
                profile["token_file"]
            )
            kite = kite_auth.get_client()
            
            # Get or create worksheet for this profile
            worksheet = sheet_manager.get_or_create_worksheet(
                sheet, 
                profile["profile_name"]
            )
            
            # Check formatting state locally (NO API CALLS)
            is_formatted = portfolio_manager._is_formatted(worksheet)
            print(f"🎨 Formatting status: {'✅ Ready' if is_formatted else '⚠️ Will format on first run'}")
            
            # Update portfolio data (smart formatting - only if needed)
            summary = portfolio_manager.update_portfolio_sheet(
                worksheet,
                kite.holdings(),
                kite.mf_holdings(),
                force_formatting=False,
                exception_list=profile.get("exception_list")
            )
            
            portfolio_summaries[profile["profile_name"]] = summary
            print(f"✅ Updated {profile['profile_name']}'s portfolio")
            
        except Exception as e:
            print(f"❌ Error processing {profile['profile_name']}: {e}")
            if "429" in str(e) or "Quota exceeded" in str(e):
                print("💡 Quota limit hit! Try minimal mode next time.")
        
        # Add delay between profiles
        print("⏳ Waiting 3 seconds...")
        time.sleep(3)
    
    # Update summary sheet
    if portfolio_summaries:
        print("\n📊 Updating summary sheet...")
        summary_sheet_name = get_summary_sheet_name()
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, summary_sheet_name)
        
        overall_summary = summary_manager.update_summary_sheet(
            summary_ws,
            portfolio_summaries,
            force_formatting=False
        )
        
        print(f"✅ Summary updated!")
        print(f"💰 Total Portfolio Value: ₹{overall_summary.total_current_value:,.2f}")


def minimal_update():
    """Minimal update - data only, no formatting API calls."""
    print("⚡ Minimal Update Mode")
    print("=" * 50)
    print("📊 Updates only data (preserves existing formatting)")
    print("🚀 Ultra-low API usage - perfect for quota limits")
    print()
    
    # Initialize managers
    sheet_manager = SheetManager("credentials.json")
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)
    
    # Get spreadsheet
    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    
    # Process each profile
    portfolio_summaries = {}
    
    for profile in get_profiles():
        print(f"\n📊 Processing {profile['profile_name']}'s data...")
        if profile.get('description'):
            print(f"   📝 {profile['description']}")
        
        try:
            # Authenticate with Kite
            kite_auth = KiteAuthManager(
                profile["api_key"],
                profile["api_secret"],
                profile["token_file"]
            )
            kite = kite_auth.get_client()
            
            # Get or create worksheet for this profile
            worksheet = sheet_manager.get_or_create_worksheet(
                sheet, 
                profile["profile_name"]
            )
            
            # Update portfolio data (NO FORMATTING)
            summary = portfolio_manager.update_data_only(
                worksheet,
                kite.holdings(),
                kite.mf_holdings(),
                exception_list=profile.get("exception_list")
            )
            
            portfolio_summaries[profile["profile_name"]] = summary
            print(f"✅ Updated {profile['profile_name']}'s data")
            
        except Exception as e:
            print(f"❌ Error processing {profile['profile_name']}: {e}")
        
        # Minimal delay
        print("⏳ Waiting 2 seconds...")
        time.sleep(2)
    
    # Update summary data
    if portfolio_summaries:
        print("\n📊 Updating summary data...")
        summary_sheet_name = get_summary_sheet_name()
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, summary_sheet_name)
        
        overall_summary = summary_manager.update_data_only(
            summary_ws,
            portfolio_summaries
        )
        
        print(f"✅ Summary data updated!")
        print(f"💰 Total Portfolio Value: ₹{overall_summary.total_current_value:,.2f}")


def force_format():
    """Force formatting on all sheets - use sparingly."""
    print("🎨 Force Format Mode")
    print("=" * 50)
    print("⚠️ This will reformat all sheets (high API usage)")
    print("🎯 Use only when you need to refresh colors/styling")
    print()
    
    confirm = input("Are you sure? This uses many API calls (y/N): ").lower().strip()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    # Initialize managers
    sheet_manager = SheetManager("credentials.json")
    portfolio_manager = PortfolioManager(sheet_manager)
    summary_manager = SummaryManager(sheet_manager)
    
    # Get spreadsheet
    spreadsheet_name = get_spreadsheet_name()
    sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
    
    # Process each profile
    portfolio_summaries = {}
    
    for profile in get_profiles():
        print(f"\n📊 Processing {profile['profile_name']}'s portfolio (with formatting)...")
        if profile.get('description'):
            print(f"   📝 {profile['description']}")
        
        try:
            # Authenticate with Kite
            kite_auth = KiteAuthManager(
                profile["api_key"],
                profile["api_secret"],
                profile["token_file"]
            )
            kite = kite_auth.get_client()
            
            # Get or create worksheet for this profile
            worksheet = sheet_manager.get_or_create_worksheet(
                sheet, 
                profile["profile_name"]
            )
            
            # Update portfolio data with forced formatting
            summary = portfolio_manager.update_portfolio_sheet(
                worksheet,
                kite.holdings(),
                kite.mf_holdings(),
                force_formatting=True,
                exception_list=profile.get("exception_list")
            )
            
            portfolio_summaries[profile["profile_name"]] = summary
            print(f"✅ Updated {profile['profile_name']}'s portfolio with formatting")
            
        except Exception as e:
            print(f"❌ Error processing {profile['profile_name']}: {e}")
            if "429" in str(e):
                print("💡 Hit quota limit during force formatting!")
                break
        
        # Longer delay for formatting mode
        print("⏳ Waiting 8 seconds...")
        time.sleep(8)
    
    # Update summary sheet with formatting
    if portfolio_summaries:
        print("\n📊 Updating summary sheet with formatting...")
        summary_sheet_name = get_summary_sheet_name()
        summary_ws = sheet_manager.get_or_create_worksheet(sheet, summary_sheet_name)
        
        overall_summary = summary_manager.update_summary_sheet(
            summary_ws,
            portfolio_summaries,
            force_formatting=True
        )
        
        print(f"✅ Summary sheet updated with formatting!")
        print(f"💰 Total Portfolio Value: ₹{overall_summary.total_current_value:,.2f}")


def show_status():
    """Show current formatting status of all sheets."""
    print("📊 Portfolio Sheet Status")
    print("=" * 50)
    
    try:
        # Initialize managers to check state
        sheet_manager = SheetManager("credentials.json")
        portfolio_manager = PortfolioManager(sheet_manager)
        summary_manager = SummaryManager(sheet_manager)
        
        # Get spreadsheet
        spreadsheet_name = get_spreadsheet_name()
        sheet = sheet_manager.get_or_create_sheet(spreadsheet_name)
        
        print(f"\n📋 Spreadsheet: {spreadsheet_name}")
        print("\n🎨 Formatting Status:")
        
        # Check each profile's formatting status
        for profile in get_profiles():
            try:
                worksheet = sheet.worksheet(profile["profile_name"])
                is_formatted = portfolio_manager._is_formatted(worksheet)
                status = "✅ Formatted" if is_formatted else "❌ Not formatted"
                print(f"  {profile['profile_name']}: {status}")
                if profile.get('description'):
                    print(f"    📝 {profile['description']}")
            except:
                print(f"  {profile['profile_name']}: ⚠️ Sheet not found")
                if profile.get('description'):
                    print(f"    📝 {profile['description']}")
        
        # Check summary sheet
        try:
            summary_sheet_name = get_summary_sheet_name()
            summary_ws = sheet.worksheet(summary_sheet_name)
            is_formatted = summary_manager._is_formatted(summary_ws)
            status = "✅ Formatted" if is_formatted else "❌ Not formatted"
            print(f"  {summary_sheet_name}: {status}")
        except:
            summary_sheet_name = get_summary_sheet_name()
            print(f"  {summary_sheet_name}: ⚠️ Sheet not found")
            
        print(f"\n📄 State files:")
        if os.path.exists(".portfolio_formatting_state.json"):
            print("  ✅ .portfolio_formatting_state.json")
        else:
            print("  ❌ .portfolio_formatting_state.json (not found)")
            
        if os.path.exists(".summary_formatting_state.json"):
            print("  ✅ .summary_formatting_state.json")
        else:
            print("  ❌ .summary_formatting_state.json (not found)")
            
    except Exception as e:
        print(f"❌ Error checking status: {e}")


def reset_formatting_state():
    """Reset formatting state (will reformat all sheets on next run)."""
    print("🔄 Reset Formatting State")
    print("=" * 50)
    print("This will delete local formatting state files.")
    print("Next update will reformat all sheets.")
    
    confirm = input("Are you sure? (y/N): ").lower().strip()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    try:
        if os.path.exists(".portfolio_formatting_state.json"):
            os.remove(".portfolio_formatting_state.json")
            print("✅ Deleted .portfolio_formatting_state.json")
        
        if os.path.exists(".summary_formatting_state.json"):
            os.remove(".summary_formatting_state.json")
            print("✅ Deleted .summary_formatting_state.json")
            
        print("🎉 Formatting state reset! Next update will reformat all sheets.")
        
    except Exception as e:
        print(f"❌ Error resetting state: {e}")


def main():
    """Main function with interactive mode selection."""
    load_dotenv()
    
    print("🚀 Kites Portfolio Tracker")
    print("=" * 50)
    print("📊 Professional portfolio tracking with intelligent quota management")
    print()
    
    while True:
        print("Choose an option:")
        print("1. 🧠 Smart Update (recommended - formats only when needed)")
        print("2. ⚡ Minimal Update (data only - ultra low API usage)")
        print("3. 🎨 Force Format (reformat everything - use sparingly)")
        print("4. 📊 Show Status (check formatting status)")
        print("5. 🔄 Reset Formatting State")
        print("6. ❌ Exit")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        try:
            if choice == "1":
                print()
                smart_update()
            elif choice == "2":
                print()
                minimal_update()
            elif choice == "3":
                print()
                force_format()
            elif choice == "4":
                print()
                show_status()
            elif choice == "5":
                print()
                reset_formatting_state()
            elif choice == "6":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-6.")
                continue
                
        except KeyboardInterrupt:
            print("\n\n⏹️ Operation cancelled by user.")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
        
        if choice in ["1", "2", "3"]:
            print("\n🎉 Operation completed!")
            print("\n💡 Pro tip: Use minimal mode for daily updates to save API quota!")
        
        # Ask if user wants to continue after operations
        if choice != "6":
            print("\n" + "="*50)
            continue_choice = input("Do you want to perform another operation? (y/N): ").lower().strip()
            if continue_choice != 'y':
                print("👋 Goodbye!")
                break
            print()  # Add spacing before next menu


if __name__ == "__main__":
    main()