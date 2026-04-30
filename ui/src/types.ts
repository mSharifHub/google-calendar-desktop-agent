export type Backend = 'local' | 'claude' | 'openai' | 'gemini';

export const SERVER_URL = 'http://127.0.0.1:8000'

export interface AgentConfig {
  backend: Backend;
  apiKey?: string;
  modelName?: string;
  sessionId: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface Thread {
  id: string;           // = session_id
  title: string;        // derived from first user message
  messages: Message[];
  config: AgentConfig;
  createdAt: number;    // timestamp ms
}

export interface StatusResponse {
  configured: boolean;
  model_info: { backend: string; model_name: string };
}
