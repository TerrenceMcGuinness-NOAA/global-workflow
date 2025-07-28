# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **2025-07-28**: Enhanced install_MCP.sh script with new features
  - Added `diff` command to show differences between source and target MCP files
  - Added `copyback` command to copy modified files back from target to source directory
  - Copyback operation includes confirmation prompt with "Are you sure (Y/n)" safety check
  - Improved file analysis with detailed status reporting (IDENTICAL, DIFFERENT, MISSING)
- **2025-07-28**: Added rocotometrics monitoring to run_all_experiments.sh script
  - Integrated `rocotometrics -v 2` call in monitor loop
  - Runs every 5 minutes during experiment execution
  - Provides enhanced workflow performance monitoring
  - Includes fallback paths for rocotometrics binary location

### Changed
- **2025-07-28**: Reorganized Jenkins agent script location
  - Moved `launch_java_agent.sh` from `dev/ci/scripts/utils/` to `dev/ci/scripts/utils/Jenkins/`
  - Updated HOMEgfs path calculation to account for new directory structure
  - Improved organization of Jenkins-related utilities

### Fixed
- **2025-07-28**: Enhanced MCP server workflow structure information
  - Fixed Python MCP server to return complete workflow structure when no specific component requested
  - Added detailed workflow descriptions including GDAS, GFS, GEFS explanations
  - Enhanced directory structure information and component descriptions
  - Improved MCP tool responsiveness for workflow structure queries
- **2025-07-28**: Fixed MCP server installation script arithmetic operations
  - Changed `((variable++))` to `variable=$((variable + 1))` for bash strict mode compatibility
  - Ensured proper operation with `set -euo pipefail`

### Infrastructure
- **2025-07-28**: Added Model Context Protocol (MCP) server integration
  - Created Python MCP server (`mcp-server.py`) for GitHub Copilot integration
  - Created Node.js MCP server (`mcp-server.js`) with official SDK
  - Added VS Code configuration for MCP server integration
  - Created installation/removal automation script (`install_MCP.sh`)
  - Added git submodule for rocoto repository on performance_metrics branch
