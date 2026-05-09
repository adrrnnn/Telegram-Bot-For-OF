"""
Database status and inspection CLI tool.

Usage:
    python cli/db_status.py              # Show database status
    python cli/db_status.py --backup     # Create backup
    python cli/db_status.py --cleanup    # Cleanup expired conversations
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager
from datetime import datetime


def show_database_status():
    """Display database status and statistics."""
    db = DatabaseManager("telegrambot.db")
    
    print("\n" + "=" * 70)
    print("TELEGRAM BOT - DATABASE STATUS")
    print("=" * 70)
    
    # Check if database exists
    if not Path("telegrambot.db").exists():
        print("✗ Database not found. Initialize with: python main.py")
        return False
    
    print(f"\nDatabase: telegrambot.db")
    print(f"Last modified: {datetime.fromtimestamp(Path('telegrambot.db').stat().st_mtime)}")
    
    # Count records in each table
    print("\nTable Statistics:")
    print("-" * 70)
    
    tables = {
        "accounts": "SELECT COUNT(*) FROM accounts",
        "profiles": "SELECT COUNT(*) FROM profiles",
        "conversations": "SELECT COUNT(*) FROM conversations",
        "api_keys": "SELECT COUNT(*) FROM api_keys",
        "api_usage_billing": "SELECT COUNT(*) FROM api_usage_billing",
        "audit_log": "SELECT COUNT(*) FROM audit_log",
        "deleted_accounts": "SELECT COUNT(*) FROM deleted_accounts",
    }
    
    total_records = 0
    for table_name, query in tables.items():
        try:
            result = db.execute_one(query)
            count = result[0] if result else 0
            total_records += count
            status = "✓" if count > 0 else "·"
            print(f"{status} {table_name:25} {count:6} records")
        except Exception as e:
            print(f"✗ {table_name:25} Error: {e}")
    
    print("-" * 70)
    print(f"Total records: {total_records}")
    
    # Show current account
    print("\nCurrent Configuration:")
    print("-" * 70)
    
    current_account = db.get_current_account()
    if current_account:
        print(f"✓ Current Account: {current_account['username']} ({current_account['email']})")
        print(f"  Status: {current_account['status']}")
        print(f"  Created: {current_account['created_at']}")
        print(f"  Last used: {current_account['last_used']}")
    else:
        print("· No accounts configured")
    
    current_profile = db.execute_one("SELECT * FROM profiles WHERE is_current = 1 LIMIT 1")
    if current_profile:
        print(f"✓ Current Profile: {current_profile['name']}")
    else:
        print("· No profiles configured")
    
    print("\n" + "=" * 70 + "\n")
    return True


def create_backup():
    """Create database backup."""
    db = DatabaseManager("telegrambot.db")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backups/telegrambot_backup_{timestamp}.db"
    
    print(f"\nCreating backup: {backup_file}")
    
    if db.backup_database(backup_file):
        print(f"✓ Backup created successfully")
        print(f"  Size: {Path(backup_file).stat().st_size / 1024:.1f} KB")
        return True
    else:
        print(f"✗ Backup failed")
        return False


def cleanup_expired():
    """Clean up expired conversations."""
    db = DatabaseManager("telegrambot.db")
    
    print("\nCleaning up expired conversations (24h+ old)...")
    
    # Get all accounts
    accounts = db.get_all_accounts()
    total_cleaned = 0
    
    for account in accounts:
        cleaned = db.cleanup_expired_conversations(account['id'], hours_to_keep=24)
        total_cleaned += cleaned
    
    if total_cleaned > 0:
        print(f"✓ Cleaned up {total_cleaned} expired conversations")
    else:
        print("· No expired conversations to clean up")
    
    return True


def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database status and management CLI")
    parser.add_argument("--backup", action="store_true", help="Create database backup")
    parser.add_argument("--cleanup", action="store_true", help="Clean up expired conversations")
    
    args = parser.parse_args()
    
    try:
        if args.backup:
            return 0 if create_backup() else 1
        elif args.cleanup:
            return 0 if cleanup_expired() else 1
        else:
            return 0 if show_database_status() else 1
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
