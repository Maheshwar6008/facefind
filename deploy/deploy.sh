#!/bin/bash
# ═════════════════════════════════════════════════════════
# FaceFind — DigitalOcean Deployment Script
# Domain: facefind.maheshwar.tech
#
# Run this on a fresh Ubuntu 22.04 droplet (4GB RAM minimum)
# Usage: bash deploy.sh
# ═════════════════════════════════════════════════════════

set -e
echo "🚀 FaceFind Deployment Starting..."
echo "   Domain: facefind.maheshwar.tech"

# ─── 1. System Setup ──────────────────────────────────────
echo ""
echo "📦 Step 1: Installing system dependencies..."
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    nginx certbot python3-certbot-nginx \
    nodejs npm git build-essential

# ─── 2. Create directories ────────────────────────────────
echo ""
echo "📁 Step 2: Setting up directories..."
sudo mkdir -p /var/www/facefind
sudo mkdir -p /var/log/facefind
sudo chown -R $USER:$USER /var/www/facefind

# ─── 3. Copy project files ────────────────────────────────
echo ""
echo "📋 Step 3: Copying project files..."
echo "   (If using git, replace this with: git clone <repo> /var/www/facefind)"
# cp -r . /var/www/facefind/
echo "   ⚠️  Please copy your project files to /var/www/facefind/"
echo "   You can use: scp -r ./* root@YOUR_DROPLET_IP:/var/www/facefind/"

# ─── 4. Backend Setup ─────────────────────────────────────
echo ""
echo "🐍 Step 4: Setting up Python backend..."
cd /var/www/facefind/backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
deactivate

# ─── 5. Frontend Build ────────────────────────────────────
echo ""
echo "🎨 Step 5: Building frontend..."
cd /var/www/facefind/frontend
npm install
npm run build

# ─── 6. Environment Config ────────────────────────────────
echo ""
echo "⚙️  Step 6: Configuring environment..."
cd /var/www/facefind

# Update .env for production
if [ -f .env ]; then
    sed -i 's/ENVIRONMENT=local/ENVIRONMENT=production/' .env
    sed -i 's|ALLOWED_ORIGINS=.*|ALLOWED_ORIGINS=https://facefind.maheshwar.tech|' .env
    echo "   ✅ .env updated for production"
    echo ""
    echo "   ⚠️  IMPORTANT: Make sure to set these in .env:"
    echo "      DRIVE_FOLDER_ID=your_folder_id"
    echo "      APP_PASSWORD=your_strong_password"
fi

# ─── 7. Google Drive Credentials ──────────────────────────
echo ""
echo "🔐 Step 7: Google Drive credentials..."
mkdir -p /var/www/facefind/backend/credentials
echo "   ⚠️  Upload your credentials.json to:"
echo "      /var/www/facefind/backend/credentials/credentials.json"

# ─── 8. Nginx Setup ───────────────────────────────────────
echo ""
echo "🌐 Step 8: Configuring Nginx..."
sudo cp /var/www/facefind/deploy/nginx.conf /etc/nginx/sites-available/facefind

# Initially set up without SSL for certbot
sudo tee /etc/nginx/sites-available/facefind-initial > /dev/null <<'EOF'
server {
    listen 80;
    server_name facefind.maheshwar.tech;

    location / {
        root /var/www/facefind/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 20M;
        proxy_read_timeout 120s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/facefind-initial /etc/nginx/sites-enabled/facefind
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# ─── 9. SSL Certificate ───────────────────────────────────
echo ""
echo "🔒 Step 9: Setting up SSL with Let's Encrypt..."
echo "   Make sure your DNS A record points to this server's IP first!"
echo ""
read -p "   Is DNS configured? (y/n): " dns_ready

if [ "$dns_ready" = "y" ]; then
    sudo certbot --nginx -d facefind.maheshwar.tech --non-interactive --agree-tos -m your@email.com
    # Now switch to the full nginx config with SSL
    sudo ln -sf /etc/nginx/sites-available/facefind /etc/nginx/sites-enabled/facefind
    sudo nginx -t && sudo systemctl reload nginx
    echo "   ✅ SSL configured!"
else
    echo "   ⏭️  Skipping SSL. Run manually later:"
    echo "      sudo certbot --nginx -d facefind.maheshwar.tech"
fi

# ─── 10. systemd Service ──────────────────────────────────
echo ""
echo "🔧 Step 10: Setting up backend service..."
sudo cp /var/www/facefind/deploy/facefind.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable facefind
sudo systemctl start facefind

# ─── 11. Set permissions ──────────────────────────────────
echo ""
echo "🔑 Step 11: Setting permissions..."
sudo chown -R www-data:www-data /var/www/facefind/backend/data
sudo chown -R www-data:www-data /var/www/facefind/backend/credentials
sudo chown -R www-data:www-data /var/log/facefind

# ─── Done ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ FaceFind deployed!"
echo ""
echo "🌐 URL:    https://facefind.maheshwar.tech"
echo ""
echo "📋 Remaining manual steps:"
echo "   1. Upload credentials.json to /var/www/facefind/backend/credentials/"
echo "   2. Set DRIVE_FOLDER_ID in /var/www/facefind/.env"
echo "   3. Set APP_PASSWORD in /var/www/facefind/.env"
echo "   4. Run preprocessing:"
echo "      cd /var/www/facefind/backend"
echo "      source venv/bin/activate"
echo "      python preprocessing.py"
echo "   5. Restart service: sudo systemctl restart facefind"
echo ""
echo "📊 Useful commands:"
echo "   sudo systemctl status facefind    # Check status"
echo "   sudo journalctl -u facefind -f    # View logs"
echo "   sudo systemctl restart facefind   # Restart"
echo "═══════════════════════════════════════════════════════"
