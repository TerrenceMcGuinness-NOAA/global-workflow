#!/usr/bin/env node

/**
 * RAG-Enhanced MCP Server for Global Workflow
 * Extends the basic MCP server with Retrieval-Augmented Generation capabilities
 */

const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} = require("@modelcontextprotocol/sdk/types.js");

const fs = require('fs').promises;
const path = require('path');

// Import RAG components (these would be installed via npm)
// const { ChromaClient } = require('chromadb');
// const { OpenAI } = require('openai');

class RAGEnhancedMCPServer {
  constructor() {
    this.server = new Server({
      name: "global-workflow-rag-mcp",
      version: "1.0.0",
    }, {
      capabilities: {
        tools: {},
      },
    });

    // Initialize vector database connection
    // this.chromaClient = new ChromaClient();
    // this.openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    
    this.setupTools();
    this.setupHandlers();
  }

  setupTools() {
    // Original tools from basic MCP server
    const originalTools = [
      {
        name: "get_workflow_structure",
        description: "Get the structure and overview of the global workflow system",
        inputSchema: {
          type: "object",
          properties: {
            component: {
              type: "string",
              description: "Specific component to focus on (optional)",
              enum: ["jobs", "scripts", "configs", "overview"]
            }
          }
        }
      },
      {
        name: "list_job_scripts",
        description: "List all available job scripts in the workflow",
        inputSchema: {
          type: "object",
          properties: {}
        }
      },
      {
        name: "get_system_configs",
        description: "Get configuration information for different HPC systems",
        inputSchema: {
          type: "object",
          properties: {
            system: {
              type: "string",
              description: "HPC system name",
              enum: ["hera", "orion", "hercules", "wcoss2", "gaeac5", "gaeac6"]
            }
          }
        }
      },
      {
        name: "explain_workflow_component",
        description: "Explain a specific workflow component or directory",
        inputSchema: {
          type: "object",
          properties: {
            component: {
              type: "string",
              description: "Component name (e.g., rocoto, gsi, ufs)",
              required: true
            }
          },
          required: ["component"]
        }
      }
    ];

    // New RAG-enhanced tools
    const ragTools = [
      {
        name: "search_documentation",
        description: "Semantic search across workflow documentation using RAG",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Natural language search query"
            },
            doc_type: {
              type: "string",
              enum: ["all", "user_guide", "dev_docs", "api_reference", "troubleshooting"],
              description: "Type of documentation to search"
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
        name: "explain_with_context",
        description: "Provide detailed explanations using RAG-enhanced context",
        inputSchema: {
          type: "object",
          properties: {
            component: {
              type: "string",
              description: "Component or concept to explain"
            },
            context_level: {
              type: "string",
              enum: ["basic", "intermediate", "advanced"],
              description: "Level of detail required"
            },
            include_examples: {
              type: "boolean",
              default: true,
              description: "Include code examples and usage patterns"
            }
          },
          required: ["component"]
        }
      },
      {
        name: "find_similar_code",
        description: "Find similar code patterns and implementations using vector similarity",
        inputSchema: {
          type: "object",
          properties: {
            code_snippet: {
              type: "string",
              description: "Code snippet to find similarities for"
            },
            language: {
              type: "string",
              enum: ["bash", "python", "cmake", "any"],
              description: "Programming language filter"
            },
            similarity_threshold: {
              type: "number",
              default: 0.7,
              description: "Minimum similarity score (0.0-1.0)"
            }
          },
          required: ["code_snippet"]
        }
      },
      {
        name: "get_operational_guidance",
        description: "Get operational procedures and best practices from knowledge base",
        inputSchema: {
          type: "object",
          properties: {
            task: {
              type: "string",
              description: "Operational task or procedure"
            },
            system: {
              type: "string",
              enum: ["hera", "orion", "hercules", "wcoss2", "gaeac5", "gaeac6"],
              description: "Target HPC system"
            },
            urgency: {
              type: "string",
              enum: ["routine", "urgent", "emergency"],
              description: "Urgency level for guidance"
            }
          },
          required: ["task"]
        }
      },
      {
        name: "analyze_workflow_dependencies",
        description: "Analyze and explain workflow job dependencies using graph knowledge",
        inputSchema: {
          type: "object",
          properties: {
            job_name: {
              type: "string",
              description: "Job name to analyze dependencies for"
            },
            direction: {
              type: "string",
              enum: ["upstream", "downstream", "both"],
              description: "Direction of dependency analysis"
            },
            depth: {
              type: "number",
              default: 2,
              description: "Depth of dependency traversal"
            }
          },
          required: ["job_name"]
        }
      }
    ];

    this.tools = [...originalTools, ...ragTools];
  }

  setupHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: this.tools,
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          // Original tool implementations (from basic MCP server)
          case "get_workflow_structure":
            return await this.getWorkflowStructure(args.component);
          case "list_job_scripts":
            return await this.listJobScripts();
          case "get_system_configs":
            return await this.getSystemConfigs(args.system);
          case "explain_workflow_component":
            return await this.explainWorkflowComponent(args.component);

          // New RAG-enhanced tool implementations
          case "search_documentation":
            return await this.searchDocumentation(args.query, args.doc_type, args.max_results);
          case "explain_with_context":
            return await this.explainWithContext(args.component, args.context_level, args.include_examples);
          case "find_similar_code":
            return await this.findSimilarCode(args.code_snippet, args.language, args.similarity_threshold);
          case "get_operational_guidance":
            return await this.getOperationalGuidance(args.task, args.system, args.urgency);
          case "analyze_workflow_dependencies":
            return await this.analyzeWorkflowDependencies(args.job_name, args.direction, args.depth);

          default:
            throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
        }
      } catch (error) {
        throw new McpError(ErrorCode.InternalError, `Error executing tool ${name}: ${error.message}`);
      }
    });
  }

  // RAG-enhanced tool implementations
  async searchDocumentation(query, docType = "all", maxResults = 5) {
    // TODO: Implement vector similarity search
    // 1. Generate embedding for query
    // 2. Search vector database
    // 3. Retrieve relevant document chunks
    // 4. Rank and return results

    // Placeholder implementation
    return {
      content: [
        {
          type: "text",
          text: `RAG Documentation Search Results for: "${query}"\n\n` +
                `Document Type: ${docType}\n` +
                `Max Results: ${maxResults}\n\n` +
                `[This would return semantically similar documentation chunks]\n\n` +
                `TODO: Implement actual vector similarity search with:\n` +
                `- Query embedding generation\n` +
                `- Vector database search\n` +
                `- Result ranking and filtering\n` +
                `- Context-aware response generation`
        }
      ],
    };
  }

  async explainWithContext(component, contextLevel = "intermediate", includeExamples = true) {
    // TODO: Implement RAG-enhanced explanation
    // 1. Retrieve relevant documentation for component
    // 2. Find related code examples
    // 3. Generate comprehensive explanation
    // 4. Include usage patterns and best practices

    return {
      content: [
        {
          type: "text",
          text: `Enhanced Explanation for: ${component}\n\n` +
                `Context Level: ${contextLevel}\n` +
                `Include Examples: ${includeExamples}\n\n` +
                `[This would provide RAG-enhanced explanations with:\n` +
                `- Retrieved documentation context\n` +
                `- Relevant code examples\n` +
                `- Best practices and usage patterns\n` +
                `- Related components and dependencies]`
        }
      ],
    };
  }

  async findSimilarCode(codeSnippet, language = "any", similarityThreshold = 0.7) {
    // TODO: Implement code similarity search
    // 1. Generate embedding for code snippet
    // 2. Search code vector database
    // 3. Filter by language and similarity threshold
    // 4. Return similar code patterns with explanations

    return {
      content: [
        {
          type: "text",
          text: `Code Similarity Search Results\n\n` +
                `Query: ${codeSnippet.substring(0, 100)}...\n` +
                `Language Filter: ${language}\n` +
                `Similarity Threshold: ${similarityThreshold}\n\n` +
                `[This would return similar code patterns with:\n` +
                `- Similarity scores\n` +
                `- Source file locations\n` +
                `- Usage context\n` +
                `- Functional explanations]`
        }
      ],
    };
  }

  async getOperationalGuidance(task, system, urgency = "routine") {
    // TODO: Implement operational guidance retrieval
    // 1. Search operational procedures database
    // 2. Filter by system and urgency
    // 3. Provide step-by-step guidance
    // 4. Include troubleshooting information

    return {
      content: [
        {
          type: "text",
          text: `Operational Guidance for: ${task}\n\n` +
                `Target System: ${system || "All systems"}\n` +
                `Urgency Level: ${urgency}\n\n` +
                `[This would provide operational guidance with:\n` +
                `- Step-by-step procedures\n` +
                `- System-specific instructions\n` +
                `- Troubleshooting steps\n` +
                `- Contact information for escalation]`
        }
      ],
    };
  }

  async analyzeWorkflowDependencies(jobName, direction = "both", depth = 2) {
    // TODO: Implement dependency analysis
    // 1. Parse workflow configurations
    // 2. Build dependency graph
    // 3. Traverse dependencies in specified direction
    // 4. Provide analysis and visualization

    return {
      content: [
        {
          type: "text",
          text: `Workflow Dependency Analysis for: ${jobName}\n\n` +
                `Analysis Direction: ${direction}\n` +
                `Traversal Depth: ${depth}\n\n` +
                `[This would provide dependency analysis with:\n` +
                `- Dependency graph visualization\n` +
                `- Critical path analysis\n` +
                `- Potential bottlenecks\n` +
                `- Impact assessment]`
        }
      ],
    };
  }

  // Original tool implementations (simplified versions)
  async getWorkflowStructure(component) {
    // Implement original functionality...
    return {
      content: [
        {
          type: "text",
          text: `Workflow structure for component: ${component || "overview"}`
        }
      ],
    };
  }

  async listJobScripts() {
    // Implement original functionality...
    return {
      content: [
        {
          type: "text",
          text: "Job scripts listing..."
        }
      ],
    };
  }

  async getSystemConfigs(system) {
    // Implement original functionality...
    return {
      content: [
        {
          type: "text",
          text: `System configuration for: ${system || "all systems"}`
        }
      ],
    };
  }

  async explainWorkflowComponent(component) {
    // Implement original functionality...
    return {
      content: [
        {
          type: "text",
          text: `Explanation of workflow component: ${component}`
        }
      ],
    };
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("RAG-Enhanced Global Workflow MCP Server running on stdio");
  }
}

// Initialize and run the server
const server = new RAGEnhancedMCPServer();
server.run().catch(console.error);
