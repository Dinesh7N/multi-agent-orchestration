#!/usr/bin/env bash
#
# Setup script for Multi-Agent Debate System
# Usage: ./setup.sh [--reset]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_CONTAINER="opencode-debate-db"
DB_USER="agent"
DB_PASS="agent"
DB_NAME="debate"
DB_PORT="15432"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCODE_DIR="$(dirname "$SCRIPTS_DIR")"

# Functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

check_command() {
    if ! command -v "$1" &> /dev/null; then
        error "$1 is required but not installed"
    fi
}

# Parse arguments
RESET=false
if [[ "$1" == "--reset" ]]; then
    RESET=true
    warn "Reset mode: will destroy existing database and volumes"
fi

echo ""
echo "==========================================="
echo "  Multi-Agent Debate System Setup"
echo "==========================================="
echo ""

# Step 0: Check prerequisites
info "Checking prerequisites..."
check_command docker
check_command docker-compose
check_command python3
check_command uv
success "All prerequisites found"

# Step 1: Handle database with docker-compose
info "Setting up infrastructure (DB, Redis, OpenCode)..."
cd "$OPENCODE_DIR"

if [[ "$RESET" == true ]]; then
    warn "Stopping and removing existing containers and volumes..."
    docker-compose down -v 2>/dev/null || true
fi

# Start services
if docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    success "Containers already running"
else
    info "Starting containers..."
    docker-compose up -d
    success "Containers started"
fi

# Wait for database to be ready
info "Waiting for database to be ready..."
for i in {1..30}; do
    if PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -p "$DB_PORT" -c "SELECT 1" &>/dev/null; then
        success "Database is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        error "Database failed to start after 30 seconds"
    fi
    sleep 1
done

# Step 2: Create virtual environment
info "Creating virtual environment..."
cd "$OPENCODE_DIR"

if [[ ! -d ".venv" ]]; then
    uv venv
    success "Virtual environment created"
else
    success "Virtual environment already exists"
fi

# Step 3: Install Python package
info "Installing Python package..."

if uv pip install -e . --quiet; then
    success "Python package installed"
else
    error "Failed to install Python package"
fi

# Step 4: Run migrations
info "Running database migrations..."

if uv run alembic upgrade head; then
    success "Migrations completed"
else
    error "Failed to run migrations"
fi

# Step 5: Verify setup
info "Verifying database tables..."
TABLE_COUNT=$(PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -p "$DB_PORT" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')

if [[ "$TABLE_COUNT" -ge 20 ]]; then
    success "Found $TABLE_COUNT tables"
else
    warn "Only found $TABLE_COUNT tables (expected 20+)"
fi

# Step 6: Test CLI
info "Testing CLI..."
if uv run debate --help &>/dev/null; then
    success "CLI is working"
else
    warn "CLI not working. Try: cd $OPENCODE_DIR && uv pip install -e . --reinstall"
fi

# Step 7: Copy agent files
info "Copying agent files to ~/.config/opencode/agent..."
TARGET_AGENT_DIR="$HOME/.config/opencode/agent"

if [[ -d "agent" ]]; then
    mkdir -p "$TARGET_AGENT_DIR"
    if cp -R agent/* "$TARGET_AGENT_DIR/"; then
        success "Agent files copied to $TARGET_AGENT_DIR"
    else
        warn "Failed to copy agent files"
    fi
else
    warn "Source agent directory not found, skipping copy"
fi

# Step 8: Configure Shell Alias
info "Configuring shell alias..."
ALIAS_CMD='alias opencode-remote="opencode --hostname localhost --port 4096"'
SHELL_RC=""

if [[ -f "$HOME/.zshrc" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -f "$HOME/.bashrc" ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [[ -n "$SHELL_RC" ]]; then
    if grep -Fxq "$ALIAS_CMD" "$SHELL_RC"; then
        success "Alias already exists in $SHELL_RC"
    else
        # Append nicely with a comment
        {
            echo ""
            echo "# OpenCode Multi-Agent Orchestration"
            echo "$ALIAS_CMD"
        } >> "$SHELL_RC"
        
        success "Alias added to $SHELL_RC"
        info "You may need to run 'source $SHELL_RC' or restart your terminal."
    fi
else
    warn "Could not find .zshrc or .bashrc. Please add the alias manually:"
    echo "  $ALIAS_CMD"
fi

# Done
echo ""
echo "==========================================="
echo -e "  ${GREEN}Setup Complete!${NC}"
echo "==========================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Test the CLI (from ~/.config/opencode/multi-agent-orchestration):"
echo "     uv run debate list-tasks"
echo "     uv run debate db-info"
echo ""
echo "  2. Start a task:"
echo "     uv run debate start \"Add authentication to the API\""
echo ""
echo "  3. Or use with OpenCode:"
echo "     opencode --agent orchestrator"
echo ""
echo "Database commands (from ~/.config/opencode/multi-agent-orchestration):"
echo "  docker-compose up -d             - Start services"
echo "  docker-compose down              - Stop services"
echo "  docker-compose logs -f           - View logs"
echo ""
