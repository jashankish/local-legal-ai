#!/usr/bin/env python3
"""
Setup script for Local Legal AI.
This script helps users initialize the application with proper configuration.
"""

import os
import sys
import secrets
import subprocess
from pathlib import Path

def generate_secret_key():
    """Generate a secure secret key for JWT."""
    return secrets.token_urlsafe(32)

def create_env_file():
    """Create .env file from .env.example with generated secrets."""
    print("🔐 Creating environment configuration...")
    
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if env_file.exists():
        response = input("⚠️  .env file already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Skipping .env file creation")
            return
    
    if not env_example.exists():
        print("❌ .env.example file not found")
        return False
    
    # Read template
    with open(env_example, 'r') as f:
        content = f.read()
    
    # Generate secret key
    secret_key = generate_secret_key()
    content = content.replace('your-secret-key-here-change-this-in-production', secret_key)
    
    # Write .env file
    with open(env_file, 'w') as f:
        f.write(content)
    
    print("✅ .env file created with generated secret key")
    print("   Please review and customize the settings as needed")
    return True

def create_directories():
    """Create necessary directories."""
    print("\n📁 Creating necessary directories...")
    
    directories = [
        "logs",
        "data",
        "uploads",
        "backend/logs",
        "backend/data"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"   ✅ {directory}/")
    
    return True

def install_dependencies():
    """Install Python dependencies."""
    print("\n📦 Installing Python dependencies...")
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], check=True, capture_output=True, text=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e.stderr}")
        return False

def check_docker():
    """Check if Docker is available."""
    print("\n🐳 Checking Docker availability...")
    
    try:
        result = subprocess.run(
            ["docker", "--version"], 
            check=True, 
            capture_output=True, 
            text=True
        )
        print(f"✅ Docker found: {result.stdout.strip()}")
        
        # Check docker-compose
        result = subprocess.run(
            ["docker-compose", "--version"], 
            check=True, 
            capture_output=True, 
            text=True
        )
        print(f"✅ Docker Compose found: {result.stdout.strip()}")
        return True
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  Docker not found. You can still run the application manually.")
        print("   Install Docker from: https://docs.docker.com/get-docker/")
        return False

def make_scripts_executable():
    """Make shell scripts executable."""
    print("\n🔧 Making scripts executable...")
    
    scripts = [
        "model/vllm_launcher.sh",
        "test_phase1.py",
        "setup.py"
    ]
    
    for script in scripts:
        script_path = Path(script)
        if script_path.exists():
            os.chmod(script_path, 0o755)
            print(f"   ✅ {script}")
    
    return True

def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "="*60)
    print("🎉 SETUP COMPLETE!")
    print("="*60)
    
    print("\n📋 Next Steps:")
    print("\n1. Review and customize your configuration:")
    print("   - Edit .env file for your specific setup")
    print("   - Adjust model settings, ChromaDB settings, etc.")
    
    print("\n2. Start the services:")
    print("   Option A - Using Docker (recommended):")
    print("     docker-compose up -d")
    
    print("\n   Option B - Manual startup:")
    print("     # Start ChromaDB")
    print("     docker run -p 8002:8000 chromadb/chroma")
    print("     # Start the backend API")
    print("     cd backend && python app.py")
    
    print("\n3. Test the installation:")
    print("   python test_phase1.py")
    
    print("\n4. Access the application:")
    print("   - API: http://localhost:8000")
    print("   - Health Check: http://localhost:8000/health")
    print("   - API Docs: http://localhost:8000/docs")
    
    print("\n5. Default admin credentials:")
    print("   - Username: admin")
    print("   - Password: admin123")
    print("   ⚠️  Change this password in production!")
    
    print("\n6. Optional - Set up LLM model:")
    print("   - Configure vLLM: model/vllm_launcher.sh")
    print("   - Or use OpenAI-compatible API endpoint")
    
    print("\n📚 Documentation:")
    print("   - README.md for detailed setup instructions")
    print("   - .env.example for configuration options")
    
    print("\n🔒 Security Notes:")
    print("   - Generated SECRET_KEY in .env file")
    print("   - Set up IP whitelisting in production")
    print("   - Use HTTPS in production")
    print("   - Regularly update dependencies")

def main():
    """Run the setup process."""
    print("🚀 Welcome to Local Legal AI Setup!")
    print("This script will help you initialize the application.\n")
    
    steps = [
        ("Environment Configuration", create_env_file),
        ("Directory Structure", create_directories),
        ("Python Dependencies", install_dependencies),
        ("Docker Check", check_docker),
        ("Script Permissions", make_scripts_executable),
    ]
    
    results = []
    
    for name, step_func in steps:
        print(f"\n{name}:")
        try:
            result = step_func()
            results.append((name, result))
        except KeyboardInterrupt:
            print("\n\n⚠️  Setup interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"❌ {name} failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 SETUP SUMMARY")
    print("="*50)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print(f"\nCompleted: {success_count}/{total_count} steps")
    
    if success_count == total_count:
        print_next_steps()
    else:
        print("\n⚠️  Some setup steps failed. Please review the errors above.")
        print("You can run this setup script again to retry failed steps.")

if __name__ == "__main__":
    main() 