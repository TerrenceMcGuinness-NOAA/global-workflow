#!/usr/bin/env node

/**
 * Simple RAG-Enhanced MCP Server for Global Workflow
 * Uses basic text search without vector embeddings for demonstration
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class SimpleRAGMCPServer {
  constructor() {
    this.server = new Server({
      name: "global-workflow-simple-rag-mcp",
      version: "1.0.0",
    }, {
      capabilities: {
        tools: {},
      },
    });

    this.knowledgeBase = null;
    this.chunks = [];
    this.documents = [];
    
    this.setupTools();
    this.setupHandlers();
    this.loadKnowledgeBase();
  }

  async loadKnowledgeBase() {
    try {
      const knowledgeDir = path.join(__dirname, 'simple-knowledge-base');
      
      const chunksData = await fs.readFile(path.join(knowledgeDir, 'chunks.json'), 'utf-8');
      this.chunks = JSON.parse(chunksData);
      
      const docsData = await fs.readFile(path.join(knowledgeDir, 'documents.json'), 'utf-8');
      this.documents = JSON.parse(docsData);
      
      const summaryData = await fs.readFile(path.join(knowledgeDir, 'summary.json'), 'utf-8');
      this.knowledgeBase = JSON.parse(summaryData);
      
      console.error(`✓ Knowledge base loaded: ${this.chunks.length} chunks from ${this.documents.length} documents`);
    } catch (error) {
      console.error('⚠ Knowledge base not found, some features may not work:', error.message);
    }
  }

  setupTools() {
    this.tools = [
      {
        name: "search_documentation",
        description: "Search through Global Workflow documentation and code",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Search query (keywords to find in documentation)"
            },
            max_results: {
              type: "number",
              default: 5,
              description: "Maximum number of results to return"
            }
          },
          required: ["query"]
        }
      },
      {
        name: "explain_component",
        description: "Get detailed explanation of a workflow component with examples",
        inputSchema: {
          type: "object",
          properties: {
            component: {
              type: "string",
              description: "Component name or concept to explain"
            },
            include_examples: {
              type: "boolean",
              default: true,
              description: "Include code examples in explanation"
            }
          },
          required: ["component"]
        }
      },
      {
        name: "list_workflow_jobs",
        description: "List available workflow jobs and scripts",
        inputSchema: {
          type: "object",
          properties: {
            filter_type: {
              type: "string",
              enum: ["all", "jobs", "scripts", "configs"],
              default: "all",
              description: "Type of workflow components to list"
            }
          }
        }
      },
      {
        name: "get_knowledge_stats",
        description: "Get statistics about the knowledge base",
        inputSchema: {
          type: "object",
          properties: {}
        }
      }
    ];
  }

  setupHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: this.tools,
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case "search_documentation":
            return await this.searchDocumentation(args.query, args.max_results);
          case "explain_component":
            return await this.explainComponent(args.component, args.include_examples);
          case "list_workflow_jobs":
            return await this.listWorkflowJobs(args.filter_type);
          case "get_knowledge_stats":
            return await this.getKnowledgeStats();
          default:
            throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
        }
      } catch (error) {
        throw new McpError(ErrorCode.InternalError, `Error executing tool ${name}: ${error.message}`);
      }
    });
  }

  searchDocumentation(query, maxResults = 5) {
    if (!this.chunks || this.chunks.length === 0) {
      return {
        content: [{
          type: "text",
          text: "Knowledge base not loaded. Please ensure the simple-processor has been run to create the knowledge base."
        }]
      };
    }

    const queryLower = query.toLowerCase();
    const results = [];
    
    for (const chunk of this.chunks) {
      const contentLower = chunk.content.toLowerCase();
      let score = 0;
      
      // Simple keyword matching with better scoring
      const queryWords = queryLower.split(/\\s+/).filter(word => word.length > 2);
      for (const word of queryWords) {
        const matches = (contentLower.match(new RegExp(word, 'g')) || []).length;
        score += matches;
        
        // Bonus for title/header matches
        if (chunk.metadata.source.toLowerCase().includes(word)) {
          score += 2;
        }
      }
      
      if (score > 0) {
        results.push({
          ...chunk,
          score
        });
      }
    }
    
    const sortedResults = results
      .sort((a, b) => b.score - a.score)
      .slice(0, maxResults);

    let responseText = `# Documentation Search Results\\n\\n`;
    responseText += `**Query:** "${query}"\\n`;
    responseText += `**Results Found:** ${sortedResults.length}\\n\\n`;

    if (sortedResults.length === 0) {
      responseText += `No matching content found. Try:\\n`;
      responseText += `- Using different keywords\\n`;
      responseText += `- Searching for specific component names\\n`;
      responseText += `- Looking for configuration terms\\n`;
    } else {
      sortedResults.forEach((result, index) => {
        responseText += `## Result ${index + 1} (Score: ${result.score})\\n`;
        responseText += `**Source:** ${result.metadata.source}\\n`;
        responseText += `**Type:** ${result.metadata.type}\\n\\n`;
        responseText += `**Content:**\\n\`\`\`\\n${result.content.substring(0, 500)}${result.content.length > 500 ? '...' : ''}\\n\`\`\`\\n\\n`;
      });
    }

    return {
      content: [{ type: "text", text: responseText }]
    };
  }

  explainComponent(component, includeExamples = true) {
    if (!this.chunks || this.chunks.length === 0) {
      return {
        content: [{
          type: "text",
          text: "Knowledge base not loaded. Please run the simple-processor first."
        }]
      };
    }

    // Search for component-related content
    const componentResults = this.searchForComponent(component);
    
    let explanation = `# ${component} - Component Explanation\\n\\n`;
    
    if (componentResults.length === 0) {
      explanation += `No specific information found for "${component}".\\n\\n`;
      explanation += `This could mean:\\n`;
      explanation += `- The component name might be spelled differently\\n`;
      explanation += `- It might be part of a larger system\\n`;
      explanation += `- Documentation might use different terminology\\n\\n`;
      explanation += `Try searching for related terms or check the workflow job listings.`;
    } else {
      explanation += `Based on the available documentation:\\n\\n`;
      
      // Group by type
      const byType = {};
      componentResults.forEach(result => {
        const type = result.metadata.type;
        if (!byType[type]) byType[type] = [];
        byType[type].push(result);
      });
      
      Object.keys(byType).forEach(type => {
        explanation += `### ${type.charAt(0).toUpperCase() + type.slice(1)} Information\\n\\n`;
        
        byType[type].slice(0, 2).forEach(result => {
          explanation += `**From:** ${result.metadata.source}\\n\\n`;
          if (includeExamples) {
            explanation += `\`\`\`\\n${result.content.substring(0, 300)}${result.content.length > 300 ? '...' : ''}\\n\`\`\`\\n\\n`;
          } else {
            explanation += `${result.content.substring(0, 150)}${result.content.length > 150 ? '...' : ''}\\n\\n`;
          }
        });
      });
    }

    return {
      content: [{ type: "text", text: explanation }]
    };
  }

  searchForComponent(component) {
    const componentLower = component.toLowerCase();
    const results = [];
    
    for (const chunk of this.chunks) {
      let score = 0;
      const contentLower = chunk.content.toLowerCase();
      const sourceLower = chunk.metadata.source.toLowerCase();
      
      // Exact component name match
      if (contentLower.includes(componentLower) || sourceLower.includes(componentLower)) {
        score += 3;
      }
      
      // Partial matches
      const componentWords = componentLower.split(/[-_\\s]/);
      for (const word of componentWords) {
        if (word.length > 2) {
          if (contentLower.includes(word)) score += 1;
          if (sourceLower.includes(word)) score += 1;
        }
      }
      
      if (score > 0) {
        results.push({ ...chunk, score });
      }
    }
    
    return results.sort((a, b) => b.score - a.score).slice(0, 10);
  }

  listWorkflowJobs(filterType = "all") {
    if (!this.documents || this.documents.length === 0) {
      return {
        content: [{
          type: "text",
          text: "Knowledge base not loaded. Please run the simple-processor first."
        }]
      };
    }

    const filtered = this.documents.filter(doc => {
      if (filterType === "all") return true;
      if (filterType === "jobs") return doc.type === "workflow" || doc.relativePath.includes("jobs");
      if (filterType === "scripts") return doc.type === "shell_script" || doc.type === "python_script";
      if (filterType === "configs") return doc.type === "configuration" || doc.type === "yaml_config";
      return false;
    });

    let response = `# Workflow Components (${filterType})\\n\\n`;
    response += `Found ${filtered.length} components:\\n\\n`;

    // Group by type
    const byType = {};
    filtered.forEach(doc => {
      const type = doc.type;
      if (!byType[type]) byType[type] = [];
      byType[type].push(doc);
    });

    Object.keys(byType).forEach(type => {
      response += `## ${type.charAt(0).toUpperCase() + type.slice(1)} (${byType[type].length})\\n\\n`;
      byType[type].slice(0, 20).forEach(doc => {
        response += `- **${doc.name}** - \`${doc.relativePath}\`\\n`;
      });
      if (byType[type].length > 20) {
        response += `  ... and ${byType[type].length - 20} more\\n`;
      }
      response += `\\n`;
    });

    return {
      content: [{ type: "text", text: response }]
    };
  }

  getKnowledgeStats() {
    if (!this.knowledgeBase) {
      return {
        content: [{
          type: "text",
          text: "Knowledge base not loaded."
        }]
      };
    }

    const typeStats = {};
    this.documents.forEach(doc => {
      typeStats[doc.type] = (typeStats[doc.type] || 0) + 1;
    });

    let stats = `# Knowledge Base Statistics\\n\\n`;
    stats += `**Created:** ${this.knowledgeBase.createdAt}\\n`;
    stats += `**Total Documents:** ${this.knowledgeBase.totalDocuments}\\n`;
    stats += `**Total Chunks:** ${this.knowledgeBase.totalChunks}\\n\\n`;
    
    stats += `## Document Types\\n\\n`;
    Object.keys(typeStats).forEach(type => {
      stats += `- **${type}:** ${typeStats[type]}\\n`;
    });
    
    stats += `\\n## Configuration\\n\\n`;
    stats += `- **Chunk Size:** ${this.knowledgeBase.config.chunkSize}\\n`;
    stats += `- **Max Files Processed:** ${this.knowledgeBase.config.maxFiles}\\n`;
    stats += `- **Supported Extensions:** ${this.knowledgeBase.config.supportedExtensions.join(', ')}\\n`;

    return {
      content: [{ type: "text", text: stats }]
    };
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Simple RAG-Enhanced Global Workflow MCP Server running on stdio");
  }
}

// Initialize and run the server
const server = new SimpleRAGMCPServer();

// Export for testing
export default SimpleRAGMCPServer;

// Run server if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  server.run().catch(console.error);
}
