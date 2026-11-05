import "dotenv/config";

import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";

import {
  StreamableHTTPClientTransport,
} from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const OLLAMA_URL = "http://localhost:11434/api/chat";
const MODEL = "qwen3:8b";

const rl = createInterface({
  input: stdin,
  output: stdout,
});

// 1. Initialize MCP client
const mcpClient = new Client({
  name: "github-ai-assistant",
  version: "1.0.0",
});

// 2. Connect to remote GitHub MCP server
const transport = new StreamableHTTPClientTransport(
  new URL("https://api.githubcopilot.com/mcp/"),
  {
    requestInit: {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_PAT}`,
      },
    },
  },
);

// 3. Convert MCP tools into Ollama tool format
let ollamaTools = [];

async function connectMCP() {
  await mcpClient.connect(transport);

  console.log("Connected to GitHub MCP!");

  const { tools } = await mcpClient.listTools();
  console.log(tools.map(t => t.name));

  ollamaTools = tools.map((tool) => ({
    type: "function",
    function: {
      name: tool.name,
      description: tool.description ?? "",
      parameters: tool.inputSchema,
    },
  }));

  console.log(`Discovered ${tools.length} GitHub tools.`);
}

// 4. Send messages to Qwen3
async function callOllama(messages) {
  const response = await fetch(OLLAMA_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      messages,
      tools: ollamaTools,
      stream: false,
    }),
  });

  if (!response.ok) {
    throw new Error(
      `Ollama error: ${response.status} ${await response.text()}`,
    );
  }

  return await response.json();
}

// 5. Execute tools requested by Qwen3
async function executeMCPTool(toolCall) {
  const name = toolCall.function.name;

  let args = toolCall.function.arguments ?? {};

  if (typeof args === "string") {
    args = JSON.parse(args);
  }

  console.log(`\nExecuting MCP tool: ${name}`);
  console.log("Arguments:", args);

  const result = await mcpClient.callTool({
    name,
    arguments: args,
  });

  console.log("Tool result:", result);

  return result;
}

// 6. Main AI conversation loop
async function chat(userInput, messages) {
  messages.push({
    role: "user",
    content: userInput,
  });

  while (true) {
    const response = await callOllama(messages);

    const assistantMessage = response.message;

    if (!assistantMessage) {
      throw new Error("No assistant message returned by Ollama");
    }

    messages.push(assistantMessage);

    const toolCalls = assistantMessage.tool_calls ?? [];

    // No more tool calls: return final answer
    if (toolCalls.length === 0) {
      console.log("\nAssistant:", assistantMessage.content);
      break;
    }

    // Execute all requested tools
    for (const toolCall of toolCalls) {
      try {
        const result = await executeMCPTool(toolCall);

        messages.push({
          role: "tool",
          tool_name: toolCall.function.name,
          content: JSON.stringify(result),
        });
      } catch (error) {
        messages.push({
          role: "tool",
          tool_name: toolCall.function.name,
          content: JSON.stringify({
            error: error.message,
          }),
        });
      }
    }
  }
}

// 7. Application entry point
async function main() {
  try {
    if (!process.env.GITHUB_PAT) {
      throw new Error("GITHUB_PAT is missing from .env");
    }

    await connectMCP();

    const messages = [
      {
        role: "system",
        content: `You are a helpful GitHub AI assistant.
You can manage GitHub repositories using available tools.
Always explain the result of operations clearly.
Ask the user for missing required information.
Never claim an operation succeeded if the tool returned an error.`,
      },
    ];

    console.log("\nGitHub AI Assistant is ready!");
    console.log("Type 'exit' to quit.");

    while (true) {
      const userInput = await rl.question("\nYou: ");

      if (userInput.trim().toLowerCase() === "exit") {
        break;
      }

      if (!userInput.trim()) {
        continue;
      }

      await chat(userInput, messages);
    }
  } catch (error) {
    console.error("\nApplication error:", error);
  } finally {
    rl.close();

    try {
      await mcpClient.close();
    } catch {
      // Ignore errors during cleanup
    }
  }
}

main();
