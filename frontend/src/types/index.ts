export interface User {
  id: string;
  email: string;
  name: string;
  is_admin?: boolean;
  role?: string;
  isGuest?: boolean;
  avatar?: string;
  dateOfBirth?: string;
  profileCompleted?: boolean;
  custom_instructions_about_user?: string;
  custom_instructions_how_to_respond?: string;
  created_at?: string;
}

export interface Citation {
  id?: string;
  chunk_id?: string;
  document: string;
  page: number;
  section?: string;
  score: number;
  snippet: string;
}

export interface WebSource {
  id?: string;
  title: string;
  url: string;
  domain: string;
  snippet: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  source_type?: 'knowledge_base' | 'web' | 'web_search' | 'combined' | 'insufficient' | 'refusal' | 'error' | 'interrupted' | 'security_policy' | 'conversational';
  selected_source?: string;
  evidence_score?: number;
  grounding_score?: number | null;
  kb_grounding_score?: number | null;
  web_grounding_score?: number | null;
  grounding_status?: string | null;
  grounding_method?: string | null;
  grounding_summary?: string | null;
  grounding_claims?: Array<{
    claim: string;
    status: 'supported' | 'partially_supported' | 'contradicted' | 'unsupported';
    supporting_source_ids: string[];
    supporting_evidence: Array<{
      evidence_id: string;
      source_type: 'knowledge_base' | 'web';
      title?: string;
      page_number?: number;
      section?: string;
      url?: string;
    }>;
    reason: string;
  }>;
  confidence?: number;
  grounding?: string;
  verification_status?: string | null;
  internal_evidence_confidence?: number;
  kb_relevance_score?: number;
  kb_threshold?: number;
  threshold?: number;
  fallback_reason?: string | null;
  web_search_used?: boolean;
  stage_timings_ms?: Record<string, number>;
  selected_evidence_quality?: number;
  kb_score?: number;
  web_score?: number;
  winning_score?: number;
  is_in_rag_pipeline?: boolean;
  external_search_used?: boolean;
  follow_up_questions?: string[];
  security_restricted?: boolean;
  violation_category?: string;
  previous_context_used?: boolean;
  used_memories?: Array<{ id: string; type: string; score: number }>;
  used_memory_ids?: string[];
  created_at: string;
  citations: Citation[];
  web_sources: WebSource[];
  visuals?: VisualItem[];
  attachments?: AttachmentItem[];
  feedback?: 'up' | 'down' | null;
  feedback_comment?: string | null;
}

export interface AttachmentItem {
  id: string;
  filename: string;
  file_type: 'image' | 'document';
  mime_type: string;
  preview_url: string;
  size_bytes: number;
  extracted_text?: string;
  vision_metadata?: Record<string, any>;
}

export interface VisualItem {
  id?: number | string;
  visual_id?: number | string;
  visual_type?: string;
  type?: string;
  title: string;
  caption: string;
  step_id?: string | null;
  status: 'pending' | 'completed' | 'failed';
  error_message?: string | null;
  mime_type?: string | null;
  asset_url?: string | null;
  is_generative?: boolean;
  created_at?: string;
}

export interface ConversationMemoryItem {
  id: string;
  user_id: string;
  memory_type: string;
  summary: string;
  entities?: any;
  provenance: string;
  status: string;
  confidence: number;
  superseded_by?: string;
  source_chat_id?: string;
  created_at: string;
  updated_at: string;
  last_accessed_at?: string;
}

export interface ScenarioMemoryItem {
  id: string;
  user_id: string;
  scenario_title: string;
  symptoms?: string;
  affected_modules?: any;
  entities?: any;
  investigation_steps?: any;
  confirmed_findings?: any;
  attempted_solutions?: any;
  unresolved_questions?: any;
  hypotheses?: any;
  status: string;
  source_chat_id?: string;
  created_at: string;
  updated_at: string;
  last_accessed_at?: string;
}

export interface Chat {
  id: string;
  user_id?: string;
  projectId?: string;
  title: string;
  created_at: string;
  updated_at: string;
  isPinned?: boolean;
  isArchived?: boolean;
  isTemporary?: boolean;
  message_count?: number;
}

export interface Project {
  id: string;
  userId?: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
  isPinned: boolean;
}

