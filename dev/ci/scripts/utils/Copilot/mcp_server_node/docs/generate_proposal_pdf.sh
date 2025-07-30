#!/bin/bash

# PDF Generation Script for MCP RAG Enhancement Proposal
# Compiles LaTeX document using XeLaTeX for better font support

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEX_FILE="${SCRIPT_DIR}/MCP_RAG_Enhancement_Proposal.tex"
PDF_FILE="${SCRIPT_DIR}/MCP_RAG_Enhancement_Proposal.pdf"

echo "MCP RAG Enhancement Proposal - PDF Generation"
echo "=============================================="
echo ""

# Check if required tools are available
echo "Checking prerequisites..."

if ! command -v xelatex &> /dev/null; then
    echo "Error: XeLaTeX not found. Please install TeX Live or MiKTeX."
    echo ""
    echo "Installation options:"
    echo "Ubuntu/Debian: sudo apt-get install texlive-xetex texlive-latex-extra"
    echo "CentOS/RHEL:   sudo yum install texlive-xetex texlive-latex"
    echo "macOS:         brew install --cask mactex"
    echo "Windows:       Download MiKTeX from https://miktex.org/"
    exit 1
fi

if ! command -v biber &> /dev/null; then
    echo "Warning: Biber not found. Bibliography processing may be limited."
fi

echo "✓ XeLaTeX found"
echo ""

# Navigate to document directory
cd "${SCRIPT_DIR}"

echo "Compiling LaTeX document..."
echo "Input file: $(basename "${TEX_FILE}")"
echo ""

# First compilation pass
echo "Pass 1: Initial compilation..."
xelatex -interaction=nonstopmode "${TEX_FILE}" > /dev/null 2>&1 || {
    echo "Error during first compilation pass. Check the log file:"
    echo "$(basename "${TEX_FILE%.*}").log"
    exit 1
}

# Second compilation pass (for cross-references)
echo "Pass 2: Resolving cross-references..."
xelatex -interaction=nonstopmode "${TEX_FILE}" > /dev/null 2>&1 || {
    echo "Error during second compilation pass."
    exit 1
}

# Clean up auxiliary files
echo "Cleaning up auxiliary files..."
rm -f *.aux *.log *.out *.toc *.fls *.fdb_latexmk *.synctex.gz

if [ -f "${PDF_FILE}" ]; then
    echo ""
    echo "✓ PDF generated successfully!"
    echo "Output file: $(basename "${PDF_FILE}")"
    echo "File size: $(ls -lh "${PDF_FILE}" | awk '{print $5}')"
    echo ""
    echo "Location: ${PDF_FILE}"
    
    # Try to open the PDF
    if command -v xdg-open &> /dev/null; then
        echo ""
        echo "Opening PDF with default viewer..."
        xdg-open "${PDF_FILE}" &
    elif command -v open &> /dev/null; then
        echo ""
        echo "Opening PDF with default viewer..."
        open "${PDF_FILE}" &
    elif command -v start &> /dev/null; then
        echo ""
        echo "Opening PDF with default viewer..."
        start "${PDF_FILE}" &
    else
        echo "PDF created but no suitable viewer found to open it automatically."
    fi
else
    echo "Error: PDF file was not created successfully."
    exit 1
fi

echo ""
echo "Document compilation completed successfully!"
echo "=========================================="
