export type Project = {
  id: string;
  name: string;
  memory_dir: string;
  output_dir: string;
  created_at: string;
  updated_at: string;
};

export type ProjectsResponse = {
  active_project_id: string;
  projects: Project[];
};

export type SystemConfig = {
  provider: string;
  compat_model: string;
  llm_trace: boolean;
  llm_timeout_seconds: number;
};

export type SetupStatus = {
  configured: boolean;
  env_exists: boolean;
  provider: string;
  missing: string[];
};

export type SetupConfig = {
  PROVIDER: string;
  OPENAI_API_KEY: string;
  OPENAI_API_KEY_MASKED?: string;
  OPENAI_MODEL: string;
  COMPAT_API_KEY: string;
  COMPAT_API_KEY_MASKED?: string;
  COMPAT_BASE_URL: string;
  COMPAT_MODEL: string;
  LLM_TIMEOUT_SECONDS: number;
  LLM_TRACE: boolean;
  LLM_PROGRESS: boolean;
  LLM_FALLBACK_ON_ERROR: boolean;
  NOVEL_PROJECTS_INDEX: string;
};

export type ChapterPlanItem = {
  chapter_number?: number;
  title?: string;
  goal?: string;
  expected_hook?: string;
  volume_number?: number;
  volume_name?: string;
  volume?: string;
  target_words?: number;
};

export type VolumePlanItem = {
  volume_number?: number;
  name?: string;
  range?: string;
  focus?: string;
  milestones?: unknown[];
};

export type StoryMemory = {
  bible?: string;
  style_guide?: string;
  genre_profile?: Record<string, unknown>;
  outline_request?: {
    user_input?: string;
    chapters?: number;
    target_words_per_chapter?: number;
  };
  chapter_plan?: {
    planned_chapters?: ChapterPlanItem[];
    volume_plan?: VolumePlanItem[];
    target_words_per_chapter?: number;
  };
  timeline?: Record<string, unknown[]>;
  characters?: Record<string, unknown[]>;
  plot_threads?: Record<string, unknown[]>;
  foreshadowing?: Record<string, unknown[]>;
  chapter_summaries?: Array<Record<string, unknown>>;
};

export type RunSummary = {
  run_id: string;
  path: string;
  chapter_number: number | null;
  chapter_title?: string;
  summary?: string;
  status?: string;
  finalized?: boolean;
  finalized_path?: string;
  finalized_at?: string;
};

export type ChapterResultResponse = {
  kind: 'result' | 'archive';
  project?: Record<string, string>;
  output_path?: string;
  result?: Record<string, unknown>;
  archive?: Record<string, unknown>;
};

export type FinalizeChapterResponse = {
  status: string;
  path: string;
  chapter_number: number;
  chapter_title: string;
  source_output_path?: string;
  text_length: number;
};

export type WorkflowEvent = {
  type: string;
  label: string;
  step?: string;
  index?: number;
  total?: number;
  duration_seconds?: number;
  elapsed_seconds: number;
  time: string;
};

export type TaskStatus = {
  task_id: string;
  label: string;
  chapter_number?: number;
  status: 'queued' | 'running' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  completed_at?: string;
  elapsed_seconds: number;
  events: WorkflowEvent[];
  result?: {
    project?: Record<string, string>;
    outline?: Record<string, unknown>;
    output_path?: string;
    chapter_number?: number;
  } | null;
  error?: string;
};

export type TopicOptions = {
  readers: string[];
  categories: string[];
};

export type TopicSuggestion = {
  title: string;
  hook: string;
  direction: string;
  opening: string;
  conflict: string;
  audience: string;
  style: string;
  outline_prompt: string;
};

export async function getProjects(): Promise<ProjectsResponse> {
  return request('/api/projects');
}

export async function getConfig(): Promise<SystemConfig> {
  return request('/api/config');
}

export async function getSetupStatus(): Promise<SetupStatus> {
  return request('/api/setup/status');
}

export async function getSetupConfig(): Promise<SetupConfig> {
  return request('/api/setup/config');
}

export async function saveSetupConfig(config: SetupConfig): Promise<SetupStatus & { status: string }> {
  return request('/api/setup/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function testSetupConfig(config: SetupConfig): Promise<{ status: string; message: string }> {
  return request('/api/setup/test', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function createProject(name: string): Promise<Project> {
  return request('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function deleteProject(projectId: string): Promise<ProjectsResponse & { deleted_project: Project }> {
  return request(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: 'DELETE',
  });
}

export async function getTopicOptions(): Promise<TopicOptions> {
  return request('/api/topic-options');
}

export async function suggestTopics(reader: string, category: string, count: number, keywords: string): Promise<{ items: TopicSuggestion[] }> {
  return request('/api/topic-suggestions', {
    method: 'POST',
    body: JSON.stringify({ reader, category, count, keywords }),
  });
}

export async function useTopicSuggestion(
  title: string,
  outlinePrompt: string,
  chapters = 30,
  targetWordsPerChapter = 3000,
): Promise<Project> {
  return request('/api/topic-suggestions/use', {
    method: 'POST',
    body: JSON.stringify({
      title,
      outline_prompt: outlinePrompt,
      chapters,
      target_words_per_chapter: targetWordsPerChapter,
    }),
  });
}

export async function activateProject(projectId: string): Promise<Project> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/activate`, {
    method: 'POST',
  });
}

export async function initMemory(projectId: string): Promise<Record<string, string>> {
  return request(`/api/memory/init?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });
}

export async function getMemory(projectId: string): Promise<StoryMemory> {
  return request(`/api/memory?project_id=${encodeURIComponent(projectId)}`);
}

export async function writeOutline(
  projectId: string,
  userInput: string,
  chapters: number,
  targetWordsPerChapter: number | null,
  resetWritingRecords = false,
): Promise<TaskStatus> {
  return request('/api/outline', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      user_input: userInput,
      chapters,
      target_words_per_chapter: targetWordsPerChapter,
      reset_writing_records: resetWritingRecords,
    }),
  });
}

export async function writeChapter(projectId: string, userInput: string): Promise<TaskStatus> {
  return request('/api/chapters/write', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      user_input: userInput,
      init_memory: true,
    }),
  });
}

export async function getTask(taskId: string): Promise<TaskStatus> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export async function getChapterResult(projectId: string, chapterNumber: number): Promise<ChapterResultResponse> {
  return request(`/api/chapters/${chapterNumber}/result?project_id=${encodeURIComponent(projectId)}`);
}

export async function finalizeChapter(projectId: string, chapterNumber: number): Promise<FinalizeChapterResponse> {
  return request(`/api/chapters/${chapterNumber}/finalize?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  });
}

export async function getRuns(projectId: string): Promise<{ project: Record<string, string>; runs: RunSummary[] }> {
  return request(`/api/runs?project_id=${encodeURIComponent(projectId)}`);
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : response.statusText;
    throw new Error(detail);
  }
  return data as T;
}
