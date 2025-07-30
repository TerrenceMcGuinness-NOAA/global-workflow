# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# Global Workflow Changelog

## 2024-07-30 - RAG Implementation Complete (Phase 1)

### Added
- **RAG-Enhanced MCP Server**: Implemented Retrieval-Augmented Generation system for intelligent documentation access
  - `simple-rag-server.js`: Basic text-search RAG implementation with 4 core tools
  - `simple-processor.js`: Document ingestion pipeline for knowledge base creation
  - `mcp-server-rag.js`: Advanced vector-based RAG server (framework ready)
  - `document-ingester.js`: Full-featured document processor with ChromaDB integration

### MCP Tools Implemented
1. **search_documentation**: Keyword-based search across workflow documentation
2. **explain_component**: Context-aware component explanations with examples
3. **list_workflow_jobs**: Categorized listing of workflow components
4. **get_knowledge_stats**: Knowledge base statistics and metadata
5. **get_documentation_references**: Access to external documentation URLs and references

### Documentation Reference System
- **documentation-references.json**: Centralized configuration for external documentation URLs
- **Categories**: Internal (Global Workflow), External (UFS, Rocoto, GSI, HPC systems, NOAA tools), Standards (Python, Shell, CMake, Fortran)
- **Environmental Equivalence (EE2)**: High-priority section for Environmental Equivalence standards integration
- **URL Management**: Structured storage with automated validation and cleanup
- **URL Validation**: Created automated validation system removing 29 invalid URLs from original 58 references
- **Quality Assurance**: All 30 remaining URLs verified as accessible and current
- **Flexible Access**: Multiple output formats (detailed, URLs only, structured JSON)
- **Comprehensive Coverage**: Validated reference URLs across NOAA ecosystem and coding standards
- **Vector Embedding Ready**: EE2 standards prioritized for first vector embedding generation
- **PR Review Integration**: EE2 standards marked for integration into PR review process

### Technical Features
- **Document Processing**: Supports 10+ file types (.md, .py, .sh, .yml, .json, etc.)
- **Smart Chunking**: Configurable chunk size with content-aware splitting
- **Knowledge Base**: JSON-based index with metadata for 707+ discovered documents
- **Search Scoring**: Keyword matching with relevance scoring and type-based filtering
- **ES Module Support**: Full conversion to modern JavaScript modules

### Architecture
- **Simple RAG**: Text-based search ready for immediate use
- **Advanced RAG**: Vector database framework with ChromaDB integration prepared
- **MCP Integration**: Seamless integration with Model Context Protocol for Copilot
- **Extensible Design**: Modular architecture for easy enhancement

### Test Results
- **Document Discovery**: Successfully processed 707 documents from Global Workflow repository
- **Knowledge Generation**: Created 53 searchable chunks from 50 test documents
- **Server Functionality**: MCP server loads knowledge base and responds to tool requests
- **Search Capability**: Basic keyword search operational with relevance scoring

### Documentation
- **README_RAG.md**: Comprehensive setup and usage guide
- **RAG_ENHANCEMENT_PLAN.md**: Technical implementation strategy
- **Test Scripts**: Automated testing for RAG components

### Next Phase (Planned)
- Vector embedding generation with sentence-transformers
- ChromaDB semantic search integration
- Full repository ingestion (remove 50-file limit)
- Advanced context-aware explanations
- Code similarity search tools

## 2024-07-30 - MCP RAG Enhancement Proposal
  - Updated MCP RAG Enhancement Proposal to focus on technical documentation ingestion
  - Added comprehensive section on Enterprise Environment 2 (EE2) standards integration
  - Included full Rocoto workflow management documentation ingestion
  - Added NOAA RDHPCS infrastructure documentation integration
  - Implemented research paper ingestion framework for scientific foundations
  - Added Parallel Works integration for secure development environments
  - Addressed GFE laptop limitations with cloud-isolated processing
  - Enhanced proposal with NOAA branding and professional formatting
  - Generated professional PDF proposal document

- **2025-01-30**: RAG-Enhanced MCP Server Implementation
  - Created comprehensive RAG (Retrieval-Augmented Generation) framework for MCP server
  - Added 5 new RAG-enhanced MCP tools:
    - `search_documentation`: Semantic search across workflow documentation
    - `explain_with_context`: Enhanced explanations using RAG context
    - `find_similar_code`: Vector similarity search for code patterns
    - `get_operational_guidance`: Procedure-specific operational help
    - `analyze_workflow_dependencies`: Intelligent dependency analysis
  - Implemented document ingestion pipeline (`document-ingester.js`)
  - Added support for multiple vector databases (ChromaDB, Pinecone, FAISS)
  - Created automated setup script (`setup-rag.sh`) with full environment configuration
  - Added comprehensive package dependencies for RAG functionality
  - Implemented metadata extraction for workflow components, phases, and systems
  - Created test framework for RAG server validation

### Enhanced
- **2025-07-30**: EE2 Vector Embedding Implementation Ready
  - Created comprehensive local embedding setup (no Hugging Face account required)
  - Added `setup_local_embeddings.py` for automated environment setup
  - Added `ee2_embedding_generator.py` for EE2 documentation processing
  - Added `embedding-options-analysis.js` for technology comparison
  - Added `EE2_EMBEDDING_SETUP.md` with complete implementation guide
  - Recommended approach: Local sentence-transformers with all-MiniLM-L6-v2 model (22MB)
  - NOAA security compliant: All processing local, no external API dependencies
  - Phase 1 ready: Immediate start with local tools, Phase 2: Production quality models
  - Integration ready: Vector embeddings prepared for RAG system and PR review process
- **2025-01-27**: Enhanced README visual design and presentation
  - Improved color scheme using NOAA brand colors (navy #003366, blue #0066cc)
  - Added professional badge styling with consistent iconography
  - Enhanced table layouts and visual hierarchy
  - Improved section organization and navigation
  - Added better visual separators and spacing
  - Enhanced typography and presentation style
  - Updated system metrics presentation with cleaner tables
  - Improved MCP integration documentation layout
  - Added department/agency attribution styling

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
