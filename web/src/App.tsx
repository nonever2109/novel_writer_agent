import { BookOpen, Check, Copy, Eye, FileText, Loader2, PenLine, Play, Plus, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ChapterPlanItem,
  ChapterResultResponse,
  FinalizeChapterResponse,
  Project,
  RunSummary,
  SetupConfig,
  SetupStatus,
  StoryMemory,
  SystemConfig,
  TaskStatus,
  TopicOptions,
  TopicSuggestion,
  VolumePlanItem,
  activateProject,
  createProject,
  deleteProject,
  getTopicOptions,
  getConfig,
  getChapterResult,
  getMemory,
  getProjects,
  getRuns,
  getSetupConfig,
  getSetupStatus,
  getTask,
  initMemory,
  finalizeChapter,
  suggestTopics,
  saveSetupConfig,
  testSetupConfig,
  useTopicSuggestion,
  writeChapter,
  writeOutline,
} from './api';
import { Button } from './components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './components/ui/dialog';
import { ScrollArea } from './components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';

type Workspace = 'topic' | 'outline' | 'writing';
type BusyState = { label: string; chapterNumber?: number } | null;
type MemoryDetailKey = 'chapter_plan' | 'chapter_summaries' | 'characters' | 'foreshadowing' | 'timeline' | 'plot_threads';

const defaultOutlinePrompt = '写一部都市悬疑小说，主角是旧档案修复师，旧城里有一宗二十年前失踪案。';

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace>('outline');
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [setupConfig, setSetupConfig] = useState<SetupConfig | null>(null);
  const [setupLoading, setSetupLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [memory, setMemory] = useState<StoryMemory | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [systemConfig, setSystemConfig] = useState<SystemConfig | null>(null);
  const [topicOptions, setTopicOptions] = useState<TopicOptions>({ readers: ['不限', '男频', '女频'], categories: ['不限'] });
  const [topicReader, setTopicReader] = useState('不限');
  const [topicCategory, setTopicCategory] = useState('不限');
  const [topicCount, setTopicCount] = useState(5);
  const [topicKeywords, setTopicKeywords] = useState('');
  const [topicSuggestions, setTopicSuggestions] = useState<TopicSuggestion[]>([]);
  const [pendingTopic, setPendingTopic] = useState<TopicSuggestion | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [outlinePrompt, setOutlinePrompt] = useState(defaultOutlinePrompt);
  const [chapterCount, setChapterCount] = useState(30);
  const [targetWordsPerChapter, setTargetWordsPerChapter] = useState(3000);
  const [selectedChapter, setSelectedChapter] = useState<ChapterPlanItem | null>(null);
  const [selectedResult, setSelectedResult] = useState<ChapterResultResponse | null>(null);
  const [resultOpen, setResultOpen] = useState(false);
  const [regenerateOutlineOpen, setRegenerateOutlineOpen] = useState(false);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [busy, setBusy] = useState<BusyState>(null);
  const [activeTask, setActiveTask] = useState<TaskStatus | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? null,
    [projects, activeProjectId],
  );
  const plannedChapters = memory?.chapter_plan?.planned_chapters ?? [];
  const generatedChapters = useMemo(() => generatedChapterNumbers(memory, runs), [memory, runs]);
  const finalizedChapters = useMemo(() => finalizedChapterNumbers(runs), [runs]);

  useEffect(() => {
    void initializeApp();
  }, []);

  useEffect(() => {
    if (activeProjectId) {
      void refreshProjectData(activeProjectId);
    }
  }, [activeProjectId]);

  async function runTask(label: string, task: () => Promise<void>, chapterNumber?: number) {
    setBusy({ label, chapterNumber });
    setActiveTask(null);
    setError('');
    setNotice('');
    try {
      await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function initializeApp() {
    setSetupLoading(true);
    setError('');
    try {
      const [status, setup] = await Promise.all([getSetupStatus(), getSetupConfig()]);
      setSetupStatus(status);
      setSetupConfig(setup);
      if (status.configured) {
        await refreshProjects();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSetupLoading(false);
    }
  }

  async function handleSetupConfigured(status: SetupStatus) {
    setSetupStatus(status);
    setSetupLoading(true);
    try {
      await refreshProjects();
    } finally {
      setSetupLoading(false);
    }
  }

  async function refreshProjects() {
    await runTask('加载项目', async () => {
      const [response, config, options] = await Promise.all([getProjects(), getConfig(), getTopicOptions()]);
      setProjects(response.projects);
      setSystemConfig(config);
      setTopicOptions(options);
      setActiveProjectId(response.active_project_id || response.projects[0]?.id || '');
    });
  }

  async function refreshProjectData(projectId = activeProjectId) {
    if (!projectId) {
      return null;
    }
    const [nextMemory, nextRuns] = await Promise.all([getMemory(projectId), getRuns(projectId)]);
    setMemory(nextMemory);
    setRuns(nextRuns.runs);
    if (nextMemory.outline_request?.user_input) {
      setOutlinePrompt(nextMemory.outline_request.user_input);
      setChapterCount(nextMemory.outline_request.chapters || chapterCount);
      setTargetWordsPerChapter(
        nextMemory.outline_request.target_words_per_chapter || nextMemory.chapter_plan?.target_words_per_chapter || 3000,
      );
    } else {
      setOutlinePrompt(defaultOutlinePrompt);
      setChapterCount(30);
      setTargetWordsPerChapter(3000);
    }
    return nextMemory;
  }

  async function handleCreateProject() {
    if (busy) {
      return;
    }
    const name = newProjectName.trim();
    if (!name) {
      setError('请输入小说名称。');
      return;
    }
    await runTask('创建小说', async () => {
      const project = await createProject(name);
      setNewProjectName('');
      await refreshProjects();
      setActiveProjectId(project.id);
      setNotice(`已创建：${project.name}`);
    });
  }

  async function handleSuggestTopics() {
    if (busy) {
      return;
    }
    await runTask('生成选题', async () => {
      const response = await suggestTopics(topicReader, topicCategory, topicCount, topicKeywords.trim());
      setTopicSuggestions(response.items);
      setNotice(`已生成 ${response.items.length} 个选题。`);
    });
  }

  async function handleUseTopic(topic: TopicSuggestion) {
    if (busy) {
      return;
    }
    await runTask('创建小说', async () => {
      const project = await useTopicSuggestion(topic.title, topic.outline_prompt, chapterCount, targetWordsPerChapter || 3000);
      const response = await getProjects();
      setProjects(response.projects);
      setActiveProjectId(project.id);
      setOutlinePrompt(topic.outline_prompt);
      setChapterCount(30);
      setTargetWordsPerChapter(3000);
      setPendingTopic(null);
      setWorkspace('outline');
      await refreshProjectData(project.id);
      setOutlinePrompt(topic.outline_prompt);
      setNotice(`已创建：${project.name}`);
    });
  }

  async function handleSelectProject(projectId: string) {
    if (busy || projectId === activeProjectId) {
      return;
    }
    setActiveProjectId(projectId);
    setSelectedChapter(null);
    setSelectedResult(null);
    setResultOpen(false);
    await runTask('切换小说', async () => {
      await activateProject(projectId);
      await refreshProjectData(projectId);
    });
  }

  async function handleDeleteActiveProject() {
    if (busy || !activeProjectId) {
      return;
    }
    await runTask('删除小说', async () => {
      const response = await deleteProject(activeProjectId);
      setProjects(response.projects);
      setActiveProjectId(response.active_project_id || response.projects[0]?.id || '');
      setDeleteProjectOpen(false);
      setNotice(`已从小说助手移除：${response.deleted_project.name}`);
    });
  }

  async function handleInitMemory() {
    if (busy || !activeProjectId) {
      return;
    }
    await runTask('初始化故事记忆', async () => {
      await initMemory(activeProjectId);
      await refreshProjectData(activeProjectId);
      setNotice('故事记忆已初始化。');
    });
  }

  async function handleWriteOutline(resetWritingRecords = false) {
    if (busy) {
      return;
    }
    if (!activeProjectId) {
      setError('请先选择小说。');
      return;
    }
    if (plannedChapters.length && !resetWritingRecords) {
      setRegenerateOutlineOpen(true);
      return;
    }
    await runTask('生成故事大纲', async () => {
      const createdTask = await writeOutline(activeProjectId, outlinePrompt.trim(), chapterCount, targetWordsPerChapter || null, resetWritingRecords);
      setActiveTask(createdTask);
      await waitForTask(createdTask.task_id);
      const refreshedMemory = await refreshProjectData(activeProjectId);
      const refreshedCount = refreshedMemory?.chapter_plan?.planned_chapters?.length ?? 0;
      if (refreshedCount === 0) {
        throw new Error('大纲任务已完成，但没有写入章节计划。请重新生成大纲。');
      }
      setWorkspace('writing');
      setRegenerateOutlineOpen(false);
      setNotice(resetWritingRecords ? '故事大纲已重新生成，旧写作记录已重置。' : '故事大纲已生成。');
    });
  }

  async function handleWriteChapter(chapter: ChapterPlanItem) {
    if (busy || !activeProjectId || !chapter.chapter_number) {
      return;
    }
    await runTask(
      generatedChapters.has(chapter.chapter_number) ? '重新写作' : '开始写作',
      async () => {
        const createdTask = await writeChapter(activeProjectId, chapterPrompt(chapter, targetWordsPerChapter));
        setActiveTask(createdTask);
        const completedTask = await waitForTask(createdTask.task_id);
        const completedChapterNumber = completedTask.result?.chapter_number || chapter.chapter_number;
        await refreshProjectData(activeProjectId);
        const result = await getChapterResult(activeProjectId, completedChapterNumber as number);
        setSelectedChapter(chapter);
        setSelectedResult(result);
        setResultOpen(true);
        setNotice(`第${completedChapterNumber}章已完成。`);
      },
      chapter.chapter_number,
    );
  }

  async function waitForTask(taskId: string): Promise<TaskStatus> {
    for (;;) {
      await delay(1000);
      const task = await getTask(taskId);
      setActiveTask(task);
      if (task.status === 'completed') {
        return task;
      }
      if (task.status === 'failed') {
        throw new Error(task.error || '任务执行失败。');
      }
    }
  }

  async function handleViewResult(chapter: ChapterPlanItem) {
    if (busy || !activeProjectId || !chapter.chapter_number) {
      return;
    }
    await runTask(
      '查看结果',
      async () => {
        const result = await getChapterResult(activeProjectId, chapter.chapter_number as number);
        setSelectedChapter(chapter);
        setSelectedResult(result);
        setResultOpen(true);
      },
      chapter.chapter_number,
    );
  }

  if (setupLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-100 text-stone-700">
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          加载配置
        </div>
      </div>
    );
  }

  if (setupStatus && !setupStatus.configured) {
    return <SetupWizard initialConfig={setupConfig} initialStatus={setupStatus} onConfigured={handleSetupConfigured} />;
  }

  return (
    <div className="grid h-screen overflow-hidden grid-cols-[292px_minmax(0,1fr)] bg-stone-100 text-stone-950 max-lg:grid-cols-1 max-lg:overflow-auto">
      <aside className="flex min-h-0 flex-col gap-5 border-r border-stone-200 bg-white p-5 max-lg:border-b max-lg:border-r-0">
        <div className="flex min-h-12 items-center gap-3">
          <BookOpen className="h-6 w-6 text-teal-700" />
          <div>
            <div className="text-xl font-semibold">小说助手 v1.0.3</div>
            <div className="text-xs text-stone-500">Novel Writer Agent</div>
          </div>
        </div>

        <label className="grid gap-2 text-sm">
          <span className="text-stone-500">当前小说</span>
          <select
            className="h-8 rounded-md border border-stone-300 bg-white px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
            value={activeProjectId}
            disabled={!!busy}
            onChange={(event) => void handleSelectProject(event.target.value)}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <div className="grid grid-cols-[minmax(0,1fr)_32px] gap-2">
          <input
            className="h-8 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
            value={newProjectName}
            disabled={!!busy}
            onChange={(event) => setNewProjectName(event.target.value)}
            placeholder="新小说名称"
          />
          <Button size="icon" disabled={!!busy} onClick={() => void handleCreateProject()} title="新建小说">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </Button>
        </div>

        {activeProject ? (
          <Card className="bg-stone-50">
            <CardContent className="grid gap-1 p-3 text-xs text-stone-500">
              <span className="text-stone-500">记忆目录</span>
              <span className="break-all">{activeProject.memory_dir}</span>
              <span className="break-all">{activeProject.output_dir}</span>
            </CardContent>
          </Card>
        ) : null}

        <Button variant="default" disabled={!!busy} onClick={() => void handleInitMemory()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {busy ? runningLabel(busy) : '初始化记忆'}
        </Button>

        <SystemConfigPanel config={systemConfig} />
      </aside>

      <main className="flex min-h-0 min-w-0 flex-col overflow-hidden p-6 max-lg:min-h-[720px] max-sm:p-4">
        <header className="mb-4 flex items-center justify-between gap-3 max-sm:flex-col max-sm:items-stretch">
          <div className="inline-flex rounded-lg border border-stone-200 bg-white p-1">
            <Button variant={workspace === 'topic' ? 'default' : 'ghost'} disabled={!!busy} onClick={() => setWorkspace('topic')}>
              <Sparkles className="h-4 w-4" />
              选题助手
            </Button>
            <Button variant={workspace === 'outline' ? 'default' : 'ghost'} disabled={!!busy} onClick={() => setWorkspace('outline')}>
              <FileText className="h-4 w-4" />
              故事大纲
            </Button>
            <Button variant={workspace === 'writing' ? 'default' : 'ghost'} disabled={!!busy} onClick={() => setWorkspace('writing')}>
              <PenLine className="h-4 w-4" />
              故事写作
            </Button>
          </div>
          <Button variant="outline" disabled={!!busy} onClick={() => void refreshProjectData()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {busy ? runningLabel(busy) : '刷新'}
          </Button>
        </header>

        <StatusBar busy={busy} task={activeTask} error={error} notice={notice} />

        {workspace === 'topic' ? (
          <TopicAssistantWorkspace
            options={topicOptions}
            reader={topicReader}
            category={topicCategory}
            count={topicCount}
            keywords={topicKeywords}
            suggestions={topicSuggestions}
            busy={busy}
            onReaderChange={setTopicReader}
            onCategoryChange={setTopicCategory}
            onCountChange={setTopicCount}
            onKeywordsChange={setTopicKeywords}
            onSuggestTopics={handleSuggestTopics}
            onUseTopic={setPendingTopic}
          />
        ) : workspace === 'outline' ? (
          <OutlineWorkspace
            activeProject={activeProject}
            memory={memory}
            outlinePrompt={outlinePrompt}
            chapterCount={chapterCount}
            targetWordsPerChapter={targetWordsPerChapter}
            busy={busy}
            onPromptChange={setOutlinePrompt}
            onChapterCountChange={setChapterCount}
            onTargetWordsPerChapterChange={setTargetWordsPerChapter}
            onWriteOutline={handleWriteOutline}
            onRequestDeleteProject={() => setDeleteProjectOpen(true)}
          />
        ) : (
            <WritingWorkspace
              chapters={plannedChapters}
              volumes={memory?.chapter_plan?.volume_plan ?? []}
              generatedChapters={generatedChapters}
              finalizedChapters={finalizedChapters}
              busy={busy}
            onWriteChapter={handleWriteChapter}
            onViewResult={handleViewResult}
          />
        )}
      </main>

      <ResultDialog
        open={resultOpen}
        onOpenChange={setResultOpen}
        projectId={activeProjectId}
        chapter={selectedChapter}
        result={selectedResult}
        onFinalized={() => void refreshProjectData()}
      />
      <ConfirmRegenerateOutlineDialog
        open={regenerateOutlineOpen}
        onOpenChange={setRegenerateOutlineOpen}
        busy={busy}
        onConfirm={() => void handleWriteOutline(true)}
      />
      <ConfirmDeleteProjectDialog
        open={deleteProjectOpen}
        project={activeProject}
        busy={busy}
        onOpenChange={setDeleteProjectOpen}
        onConfirm={() => void handleDeleteActiveProject()}
      />
      <ConfirmUseTopicDialog
        topic={pendingTopic}
        busy={busy}
        onOpenChange={(open) => !open && setPendingTopic(null)}
        onConfirm={() => pendingTopic && void handleUseTopic(pendingTopic)}
      />
    </div>
  );
}

function SetupWizard({
  initialConfig,
  initialStatus,
  onConfigured,
}: {
  initialConfig: SetupConfig | null;
  initialStatus: SetupStatus;
  onConfigured: (status: SetupStatus) => Promise<void>;
}) {
  const [form, setForm] = useState<SetupConfig>(
    initialConfig ?? {
      PROVIDER: 'openai_compatible',
      OPENAI_API_KEY: '',
      OPENAI_MODEL: 'gpt-4.1-mini',
      COMPAT_API_KEY: '',
      COMPAT_BASE_URL: 'https://openrouter.ai/api/v1',
      COMPAT_MODEL: '',
      LLM_TIMEOUT_SECONDS: 600,
      LLM_TRACE: false,
      LLM_PROGRESS: true,
      LLM_FALLBACK_ON_ERROR: false,
      NOVEL_PROJECTS_INDEX: 'novel_projects.json',
    },
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function runSetupTask(label: string, task: () => Promise<void>) {
    setBusy(label);
    setError('');
    setNotice('');
    try {
      await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy('');
    }
  }

  async function handleTest() {
    await runSetupTask('测试连接', async () => {
      const result = await testSetupConfig(form);
      setNotice(result.message || '连接测试成功。');
    });
  }

  async function handleSave() {
    await runSetupTask('保存配置', async () => {
      const result = await saveSetupConfig(form);
      await onConfigured(result);
    });
  }

  const provider = form.PROVIDER;
  return (
    <div className="min-h-screen bg-stone-100 p-6 text-stone-950 max-sm:p-4">
      <div className="mx-auto grid max-w-3xl gap-4">
        <div className="flex items-center gap-3">
          <BookOpen className="h-7 w-7 text-teal-700" />
          <div>
            <h1 className="text-2xl font-semibold">小说助手首次配置</h1>
            <p className="text-sm text-stone-500">填写 AI 服务参数后即可进入 Web 写作界面。</p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">基础配置</CardTitle>
            <p className="text-sm text-stone-500">
              当前缺少：{initialStatus.missing.length ? initialStatus.missing.join('、') : '关键配置'}
            </p>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">AI 服务商</span>
              <select
                className="h-8 rounded-md border border-stone-300 bg-white px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700"
                value={form.PROVIDER}
                disabled={!!busy}
                onChange={(event) => setForm({ ...form, PROVIDER: event.target.value })}
              >
                <option value="openai_compatible">OpenAI Compatible</option>
                <option value="openai">OpenAI</option>
                <option value="mock">Mock</option>
              </select>
            </label>

            {provider === 'openai' ? (
              <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                <SecretInput
                  label="API Key"
                  value={form.OPENAI_API_KEY}
                  masked={form.OPENAI_API_KEY_MASKED}
                  disabled={!!busy}
                  onChange={(value) => setForm({ ...form, OPENAI_API_KEY: value })}
                />
                <TextInput
                  label="模型"
                  value={form.OPENAI_MODEL}
                  disabled={!!busy}
                  placeholder="gpt-4.1-mini"
                  onChange={(value) => setForm({ ...form, OPENAI_MODEL: value })}
                />
              </div>
            ) : null}

            {provider === 'openai_compatible' || provider === 'compatible' ? (
              <div className="grid gap-3">
                <TextInput
                  label="API 地址"
                  value={form.COMPAT_BASE_URL}
                  disabled={!!busy}
                  placeholder="https://openrouter.ai/api/v1"
                  onChange={(value) => setForm({ ...form, COMPAT_BASE_URL: value })}
                />
                <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                  <SecretInput
                    label="API Key"
                    value={form.COMPAT_API_KEY}
                    masked={form.COMPAT_API_KEY_MASKED}
                    disabled={!!busy}
                    onChange={(value) => setForm({ ...form, COMPAT_API_KEY: value })}
                  />
                  <TextInput
                    label="模型"
                    value={form.COMPAT_MODEL}
                    disabled={!!busy}
                    placeholder="openai/gpt-4.1-mini"
                    onChange={(value) => setForm({ ...form, COMPAT_MODEL: value })}
                  />
                </div>
              </div>
            ) : null}

            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">超时时间</span>
              <input
                className="h-8 w-36 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700"
                type="number"
                min={1}
                max={3600}
                value={form.LLM_TIMEOUT_SECONDS}
                disabled={!!busy}
                onChange={(event) => setForm({ ...form, LLM_TIMEOUT_SECONDS: Number(event.target.value) })}
              />
            </label>

            <button
              className="text-left text-sm font-medium text-teal-700"
              type="button"
              onClick={() => setAdvancedOpen(!advancedOpen)}
            >
              {advancedOpen ? '收起高级配置' : '展开高级配置'}
            </button>
            {advancedOpen ? (
              <div className="grid gap-3 rounded-md border border-stone-200 bg-stone-50 p-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.LLM_TRACE}
                    disabled={!!busy}
                    onChange={(event) => setForm({ ...form, LLM_TRACE: event.target.checked })}
                  />
                  调试日志 LLM_TRACE
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.LLM_PROGRESS}
                    disabled={!!busy}
                    onChange={(event) => setForm({ ...form, LLM_PROGRESS: event.target.checked })}
                  />
                  控制台进度 LLM_PROGRESS
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={false}
                    disabled
                    onChange={() => undefined}
                  />
                  模型失败时使用 fallback（已关闭，真实模型失败会直接报错）
                </label>
                <TextInput
                  label="项目索引文件"
                  value={form.NOVEL_PROJECTS_INDEX}
                  disabled={!!busy}
                  placeholder="novel_projects.json"
                  onChange={(value) => setForm({ ...form, NOVEL_PROJECTS_INDEX: value })}
                />
              </div>
            ) : null}

            {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
            {notice ? <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</div> : null}

            <div className="flex justify-end gap-2">
              <Button variant="outline" disabled={!!busy} onClick={() => void handleTest()}>
                {busy === '测试连接' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                测试连接
              </Button>
              <Button disabled={!!busy} onClick={() => void handleSave()}>
                {busy === '保存配置' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                保存并进入
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TextInput({
  label,
  value,
  disabled,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  disabled?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="text-stone-500">{label}</span>
      <input
        className="h-8 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SecretInput({
  label,
  value,
  masked,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  masked?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="text-stone-500">{label}</span>
      <input
        className="h-8 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
        value={value}
        disabled={disabled}
        placeholder={masked ? `已保存：${masked}，留空表示不修改` : '输入 API Key'}
        type="password"
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function StatusBar({ busy, task, error, notice }: { busy: BusyState; task: TaskStatus | null; error: string; notice: string }) {
  if (busy) {
    return (
      <div className="mb-3 rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          {busy.chapterNumber ? `第${busy.chapterNumber}章：${busy.label}` : busy.label}
          {task ? <span className="text-xs text-teal-700">已用时 {formatDuration(task.elapsed_seconds)}</span> : null}
        </div>
        {task ? <TaskProgress task={task} /> : <WorkflowProgress busy={busy} />}
      </div>
    );
  }
  if (error) {
    return <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>;
  }
  if (notice) {
    return <div className="mb-3 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</div>;
  }
  return null;
}

function TaskProgress({ task }: { task: TaskStatus }) {
  const latestStep = [...task.events].reverse().find((event) => event.index && event.total);
  const completedSteps = task.events.filter((event) => event.type === 'step_completed');
  const visibleEvents = task.events.slice(-8);
  return (
    <div className="mt-2 grid gap-2">
      {latestStep?.index && latestStep.total ? (
        <div className="h-1.5 overflow-hidden rounded-full bg-white/70">
          <div
            className="h-full bg-teal-600 transition-all"
            style={{ width: `${Math.min(100, (completedSteps.length / latestStep.total) * 100)}%` }}
          />
        </div>
      ) : null}
      <div className="grid gap-1 text-xs">
        {visibleEvents.map((event, index) => (
          <div key={`${event.time}-${index}`} className="flex items-center justify-between gap-3 rounded-md bg-white/60 px-2 py-1">
            <span>
              {event.index && event.total ? `${event.index}/${event.total} ` : ''}
              {eventLabel(event)}
            </span>
            <span className="shrink-0 text-teal-700">
              {event.duration_seconds ? `${event.duration_seconds}s` : formatDuration(event.elapsed_seconds)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkflowProgress({ busy }: { busy: BusyState }) {
  if (!busy) {
    return null;
  }
  const stages = busy.chapterNumber
    ? ['读取故事记忆', '规划章节', '生成场景正文', '检查与润色', '更新故事记忆', '写入输出记录']
    : busy.label.includes('大纲')
      ? ['读取项目配置', '生成故事框架', '生成章节计划', '写入故事记忆']
      : [];
  if (!stages.length) {
    return null;
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
      {stages.map((stage) => (
        <span key={stage} className="rounded-full bg-white/70 px-2 py-1 text-teal-700">
          {stage}
        </span>
      ))}
    </div>
  );
}

function runningLabel(busy: BusyState): string {
  if (!busy) {
    return '';
  }
  if (busy.chapterNumber) {
    return `第${busy.chapterNumber}章写作中`;
  }
  if (busy.label.includes('大纲')) {
    return '大纲生成中';
  }
  return `${busy.label}中`;
}

function ConfirmRegenerateOutlineDialog({
  open,
  onOpenChange,
  busy,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: BusyState;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(520px,94vw)]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">是否重新生成大纲？</DialogTitle>
          <DialogDescription className="text-sm text-stone-500">
            重新生成大纲将重置之前的写作记录，包括章节归档和已生成的章节输出。
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!!busy} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!!busy} onClick={onConfirm}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            重新生成大纲
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDeleteProjectDialog({
  open,
  project,
  busy,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  project: Project | null;
  busy: BusyState;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(560px,94vw)]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">是否删除这个小说？</DialogTitle>
          <DialogDescription className="text-sm text-stone-500">
            删除后《{project?.name || '当前小说'}》将无法再使用小说助手写作，但可以在 {projectRoot(project)} 目录下查看原始写作记录。
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-md bg-stone-50 p-3 text-sm leading-6 text-stone-700">
          该操作只会从小说助手列表中移除项目，不会删除磁盘上的项目目录和输出文件。
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!!busy} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!!busy} onClick={onConfirm}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            删除小说
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmUseTopicDialog({
  topic,
  busy,
  onOpenChange,
  onConfirm,
}: {
  topic: TopicSuggestion | null;
  busy: BusyState;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={!!topic} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(560px,94vw)]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">是否使用这个题材？</DialogTitle>
          <DialogDescription className="text-sm text-stone-500">
            确认后会用《{topic?.title || '未命名'}》创建新的小说项目，目录按 novel-1、novel-2 递增，并把选题内容填入故事大纲。
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-md bg-stone-50 p-3 text-sm leading-6 text-stone-700">{topic?.hook}</div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!!busy} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!!busy} onClick={onConfirm}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            使用这个题材
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TopicAssistantWorkspace(props: {
  options: TopicOptions;
  reader: string;
  category: string;
  count: number;
  keywords: string;
  suggestions: TopicSuggestion[];
  busy: BusyState;
  onReaderChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onCountChange: (value: number) => void;
  onKeywordsChange: (value: string) => void;
  onSuggestTopics: () => Promise<void>;
  onUseTopic: (topic: TopicSuggestion) => void;
}) {
  return (
    <section className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">选题助手</CardTitle>
          <p className="text-sm text-stone-500">根据读者、分类和关键词生成可直接用于故事大纲的选题方向。</p>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid grid-cols-[160px_180px_120px_minmax(0,1fr)_auto] items-end gap-3 max-xl:grid-cols-2 max-sm:grid-cols-1">
            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">选择读者</span>
              <select
                className="h-8 rounded-md border border-stone-300 bg-white px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
                value={props.reader}
                disabled={!!props.busy}
                onChange={(event) => props.onReaderChange(event.target.value)}
              >
                {props.options.readers.map((reader) => (
                  <option key={reader} value={reader}>
                    {reader}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">选择分类</span>
              <select
                className="h-8 rounded-md border border-stone-300 bg-white px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
                value={props.category}
                disabled={!!props.busy}
                onChange={(event) => props.onCategoryChange(event.target.value)}
              >
                {props.options.categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">生成数量</span>
              <select
                className="h-8 rounded-md border border-stone-300 bg-white px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
                value={props.count}
                disabled={!!props.busy}
                onChange={(event) => props.onCountChange(Number(event.target.value))}
              >
                {[3, 5, 8, 10].map((count) => (
                  <option key={count} value={count}>
                    {count}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm">
              <span className="text-stone-500">关键词/偏好</span>
              <input
                className="h-8 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
                value={props.keywords}
                disabled={!!props.busy}
                onChange={(event) => props.onKeywordsChange(event.target.value)}
                placeholder="旧城、文物修复、悬疑、双强"
              />
            </label>
            <Button disabled={!!props.busy} onClick={() => void props.onSuggestTopics()}>
              {props.busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {props.busy ? runningLabel(props.busy) : '生成选题'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="min-h-0 overflow-y-auto pr-2">
        {props.suggestions.length ? (
          <div className="grid grid-cols-2 gap-3 max-xl:grid-cols-1">
            {props.suggestions.map((topic, index) => (
              <TopicSuggestionCard
                key={`${topic.title}-${index}`}
                topic={topic}
                busy={props.busy}
                onUseTopic={props.onUseTopic}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-stone-300 bg-white/60 p-8 text-stone-500">
            选择读者和分类后系统自动生成热门选题，可使用生成的题材开始写作大纲。
          </div>
        )}
      </div>
    </section>
  );
}

function TopicSuggestionCard({
  topic,
  busy,
  onUseTopic,
}: {
  topic: TopicSuggestion;
  busy: BusyState;
  onUseTopic: (topic: TopicSuggestion) => void;
}) {
  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-lg">{topic.title}</CardTitle>
            <p className="mt-1 text-sm leading-6 text-stone-600">{topic.hook || '暂无卖点。'}</p>
          </div>
          <Button className="shrink-0 whitespace-nowrap" size="sm" disabled={!!busy} onClick={() => onUseTopic(topic)}>
            <Sparkles className="h-4 w-4" />
            使用这个题材
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <InfoLine label="写作方向" value={topic.direction || '暂无'} />
        <InfoLine label="开篇切入" value={topic.opening || '暂无'} />
        <InfoLine label="核心冲突" value={topic.conflict || '暂无'} />
        <InfoLine label="目标读者" value={topic.audience || '暂无'} />
        <InfoLine label="风格要求" value={topic.style || '暂无'} />
        <div className="rounded-md bg-stone-50 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-stone-500">大纲输入稿</span>
            <Button size="sm" variant="outline" onClick={() => void navigator.clipboard?.writeText(topic.outline_prompt)}>
              <Copy className="h-4 w-4" />
              复制
            </Button>
          </div>
          <p className="max-h-40 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-stone-700">{topic.outline_prompt}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function OutlineWorkspace(props: {
  activeProject: Project | null;
  memory: StoryMemory | null;
  outlinePrompt: string;
  chapterCount: number;
  targetWordsPerChapter: number;
  busy: BusyState;
  onPromptChange: (value: string) => void;
  onChapterCountChange: (value: number) => void;
  onTargetWordsPerChapterChange: (value: number) => void;
  onWriteOutline: () => Promise<void>;
  onRequestDeleteProject: () => void;
}) {
  const plannedCount = props.memory?.chapter_plan?.planned_chapters?.length ?? 0;
  return (
    <section className="grid min-h-0 flex-1 content-start gap-5 overflow-auto pr-2">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle className="text-xl">故事大纲</CardTitle>
            <p className="mt-1 text-sm text-stone-500">{plannedCount ? `${plannedCount} 章计划` : '未生成章节计划'}</p>
          </div>
        </CardHeader>
        <CardContent>
          <textarea
            className="min-h-32 w-full resize-y rounded-md border border-stone-300 p-2.5 text-sm leading-6 outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500"
            value={props.outlinePrompt}
            disabled={!!props.busy}
            onChange={(event) => props.onPromptChange(event.target.value)}
            placeholder="输入小说题材、主角、核心冲突和读者期待"
          />
          <div className="mt-3 flex items-center justify-start gap-3 max-sm:flex-wrap">
            <label className="flex items-center gap-2 text-sm">
              <span className="shrink-0 text-stone-500">章节数</span>
              <input
                className="h-8 w-24 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500"
                type="number"
                min={1}
                max={2000}
                value={props.chapterCount}
                disabled={!!props.busy}
                onChange={(event) => props.onChapterCountChange(Number(event.target.value))}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <span className="shrink-0 text-stone-500">每章字数</span>
              <input
                className="h-8 w-28 rounded-md border border-stone-300 px-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500"
                type="number"
                min={100}
                max={50000}
                step={100}
                value={props.targetWordsPerChapter}
                disabled={!!props.busy}
                onChange={(event) => props.onTargetWordsPerChapterChange(Number(event.target.value))}
              />
            </label>
            <Button onClick={() => void props.onWriteOutline()} disabled={!!props.busy}>
              {props.busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {props.busy ? runningLabel(props.busy) : plannedCount ? '重新生成大纲' : '生成大纲'}
            </Button>
          </div>
        </CardContent>
      </Card>
      <MemorySnapshot memory={props.memory} />
      <ProjectDeleteCard activeProject={props.activeProject} busy={props.busy} onRequestDelete={props.onRequestDeleteProject} />
    </section>
  );
}

function ProjectDeleteCard({
  activeProject,
  busy,
  onRequestDelete,
}: {
  activeProject: Project | null;
  busy: BusyState;
  onRequestDelete: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">故事删除</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4 max-md:flex-col max-md:items-stretch">
        <p className="text-sm leading-6 text-stone-600">
          删除后该小说将无法再使用小说助手写作，但可以在 {projectRoot(activeProject)} 目录下查看原始写作记录。
        </p>
        <Button variant="outline" disabled={!!busy || !activeProject} onClick={onRequestDelete}>
          <Trash2 className="h-4 w-4" />
          删除小说
        </Button>
      </CardContent>
    </Card>
  );
}

function WritingWorkspace(props: {
  chapters: ChapterPlanItem[];
  volumes: VolumePlanItem[];
  generatedChapters: Set<number>;
  finalizedChapters: Set<number>;
  busy: BusyState;
  onWriteChapter: (chapter: ChapterPlanItem) => Promise<void>;
  onViewResult: (chapter: ChapterPlanItem) => Promise<void>;
}) {
  return (
    <section className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-3">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">故事写作</h1>
        <span className="text-sm text-stone-500">{props.chapters.length ? `${props.chapters.length} 章` : '等待大纲'}</span>
      </div>
      {props.chapters.length ? (
        <div className="grid min-h-0 gap-3 overflow-y-auto pr-2">
          {props.chapters.map((chapter) => (
            <ChapterCard
              key={chapter.chapter_number ?? chapter.title}
              chapter={chapter}
              volumes={props.volumes}
              generated={!!chapter.chapter_number && props.generatedChapters.has(chapter.chapter_number)}
              finalized={!!chapter.chapter_number && props.finalizedChapters.has(chapter.chapter_number)}
              busy={props.busy}
              onWriteChapter={props.onWriteChapter}
              onViewResult={props.onViewResult}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-stone-300 bg-white/60 p-8 text-stone-500">
          先在“故事大纲”生成章节计划。
        </div>
      )}
    </section>
  );
}

function ChapterCard(props: {
  chapter: ChapterPlanItem;
  volumes: VolumePlanItem[];
  generated: boolean;
  finalized: boolean;
  busy: BusyState;
  onWriteChapter: (chapter: ChapterPlanItem) => Promise<void>;
  onViewResult: (chapter: ChapterPlanItem) => Promise<void>;
}) {
  const volumeText = chapterVolumeLabel(props.chapter, props.volumes);
  return (
    <Card>
      <CardContent className="grid grid-cols-[52px_minmax(0,1fr)] gap-4 p-4 max-sm:grid-cols-1">
        <div className="flex h-12 w-12 items-center justify-center rounded-md bg-teal-50 text-xl font-semibold text-teal-700">
          {props.chapter.chapter_number ?? '-'}
        </div>
        <div className="min-w-0">
          {volumeText ? <div className="mb-1 text-sm font-medium text-stone-500">{volumeText}</div> : null}
          <div className="flex items-center justify-between gap-3">
            <h2 className="truncate text-lg font-semibold">{chapterDisplayTitle(props.chapter)}</h2>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-3">
              {props.generated ? (
                <span className="inline-flex items-center gap-1 text-sm text-teal-700">
                  <Check className="h-3.5 w-3.5" />
                  已生成
                </span>
              ) : null}
              {props.finalized ? (
                <span className="inline-flex items-center gap-1 text-sm text-teal-700">
                  <Check className="h-3.5 w-3.5" />
                  已定稿
                </span>
              ) : null}
            </div>
          </div>
          <p className="mt-2 leading-7 text-stone-700">{props.chapter.goal || '暂无章节目标。'}</p>
          {props.chapter.expected_hook ? <p className="mt-1 text-sm text-stone-500">{props.chapter.expected_hook}</p> : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" disabled={!!props.busy} onClick={() => void props.onWriteChapter(props.chapter)}>
              {props.busy?.chapterNumber === props.chapter.chapter_number ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PenLine className="h-4 w-4" />
              )}
              {props.busy?.chapterNumber === props.chapter.chapter_number
                ? '写作中'
                : props.generated
                  ? '重新写作'
                  : '开始写作'}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!!props.busy || !props.generated}
              onClick={() => void props.onViewResult(props.chapter)}
            >
              <Eye className="h-4 w-4" />
              查看结果
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function chapterDisplayTitle(chapter: ChapterPlanItem) {
  const number = chapter.chapter_number ? `第${chapter.chapter_number}章` : '';
  if (!number) {
    return chapter.title || '未命名章节';
  }
  return chapter.title ? `${number} ${chapter.title}` : number;
}

function chapterVolumeLabel(chapter: ChapterPlanItem, volumes: VolumePlanItem[] = []) {
  const matchedVolume = volumeForChapter(chapter, volumes);
  const volumeNumber = chapter.volume_number ?? matchedVolume?.volume_number;
  const rawName = chapter.volume_name || chapter.volume || matchedVolume?.name || '';
  if (!volumeNumber && !rawName) {
    return '';
  }
  if (!volumeNumber) {
    return rawName;
  }
  const name = stripVolumePrefix(rawName);
  return name ? `第${volumeNumber}卷-${name}` : `第${volumeNumber}卷`;
}

function ResultDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  chapter: ChapterPlanItem | null;
  result: ChapterResultResponse | null;
  onFinalized: () => void;
}) {
  const result = props.result?.result;
  const [finalizing, setFinalizing] = useState(false);
  const [finalized, setFinalized] = useState<FinalizeChapterResponse | null>(null);
  const [finalizeError, setFinalizeError] = useState('');
  const versions = chapterVersions(result);
  const reports = pickJson(result, [
    'continuity_report',
    'chapter_safety_report',
    'final_safety_report',
    'chapter_eval_report',
    'memory_validation_report',
  ]);
  const memoryUpdate = pickJson(result, ['chapter_archive', 'memory_update']);
  const archive = props.result?.archive;
  const finalText = getString(result, 'final_chapter') || getString(archive, 'summary');
  const defaultResultTab = finalText ? 'final' : 'raw';
  const canFinalize = !!props.projectId && !!props.chapter?.chapter_number && !!getString(result, 'final_chapter');

  useEffect(() => {
    setFinalized(null);
    setFinalizeError('');
  }, [props.open, props.chapter?.chapter_number, props.result?.output_path]);

  async function handleFinalize() {
    if (!props.projectId || !props.chapter?.chapter_number) {
      return;
    }
    setFinalizing(true);
    setFinalizeError('');
    setFinalized(null);
    try {
      const response = await finalizeChapter(props.projectId, props.chapter.chapter_number);
      setFinalized(response);
      props.onFinalized();
    } catch (err) {
      setFinalizeError(err instanceof Error ? err.message : String(err));
    } finally {
      setFinalizing(false);
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <DialogTitle className="text-xl font-semibold">
                {props.chapter?.chapter_number ? `第${props.chapter.chapter_number}章` : '章节结果'}
                {props.chapter?.title ? `：${props.chapter.title}` : ''}
              </DialogTitle>
              <DialogDescription className="mt-1 break-all text-sm text-stone-500">
                {props.result?.output_path || (archive ? '来自章节归档' : '暂无输出路径')}
              </DialogDescription>
            </div>
            <Button className="mr-8 shrink-0" disabled={!canFinalize || finalizing} onClick={() => void handleFinalize()}>
              {finalizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
              定稿
            </Button>
          </div>
          {finalized ? (
            <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              已定稿：<span className="break-all">{finalized.path}</span>
            </div>
          ) : null}
          {finalizeError ? <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{finalizeError}</div> : null}
        </DialogHeader>

        <Tabs
          key={`${props.result?.output_path || props.chapter?.chapter_number || 'empty'}:${defaultResultTab}`}
          defaultValue={defaultResultTab}
          className="min-h-0"
        >
          <TabsList className="flex-wrap">
            <TabsTrigger value="final">最终正文</TabsTrigger>
            <TabsTrigger value="compare">写作对比</TabsTrigger>
            <TabsTrigger value="reports">评估报告</TabsTrigger>
            <TabsTrigger value="memory">记忆更新</TabsTrigger>
            <TabsTrigger value="raw">原始数据</TabsTrigger>
          </TabsList>

          <TabsContent value="final">
            <TextViewer value={finalText || '暂无正文。'} />
          </TabsContent>

          <TabsContent value="compare">
            {versions.length ? (
              <div className="overflow-x-auto pb-2">
                <div
                  className="grid gap-3"
                  style={{
                    gridTemplateColumns: `repeat(${versions.length}, minmax(320px, 1fr))`,
                    minWidth: `${versions.length * 340}px`,
                  }}
                >
                  {versions.map((version) => (
                    <Card key={version.label} className="min-w-0">
                      <CardHeader>
                        <CardTitle>{version.label}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <TextViewer value={version.value} compact />
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyPanel text="当前结果没有可对比的章节版本。" />
            )}
          </TabsContent>

          <TabsContent value="reports">
            <ReportsPanel reports={reports} />
          </TabsContent>

          <TabsContent value="memory">
            <MemoryUpdatePanel archive={archive} memoryUpdate={memoryUpdate.memory_update} />
          </TabsContent>

          <TabsContent value="raw">
            <JsonViewer value={props.result ?? {}} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function MemorySnapshot({ memory }: { memory: StoryMemory | null }) {
  const [detailKey, setDetailKey] = useState<MemoryDetailKey | null>(null);
  const stats = [
    { key: 'chapter_plan' as const, label: '章节计划', value: memory?.chapter_plan?.planned_chapters?.length ?? 0 },
    { key: 'chapter_summaries' as const, label: '章节归档', value: memory?.chapter_summaries?.length ?? 0 },
    { key: 'characters' as const, label: '角色记录', value: arrayCount(memory?.characters?.characters) },
    { key: 'foreshadowing' as const, label: '伏笔记录', value: arrayCount(memory?.foreshadowing?.items) },
    { key: 'timeline' as const, label: '时间线', value: arrayCount(memory?.timeline?.events) },
    { key: 'plot_threads' as const, label: '主线/支线/悬念线', value: arrayCount(memory?.plot_threads?.threads) },
  ];
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">故事记忆</CardTitle>
          <p className="text-sm text-stone-500">当前项目</p>
        </CardHeader>
        <CardContent className="grid min-h-0 grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)] gap-4 max-xl:grid-cols-1">
          <div className="grid min-h-0 content-start gap-3">
            <MemoBlock title="故事框架（Story Bible）" value={memory?.bible} />
            <MemoBlock title="写作风格（Style Guide）" value={memory?.style_guide} />
          </div>
          <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {stats.map((item) => (
              <button
                key={item.key}
                className="rounded-md border border-stone-200 p-3 text-left transition hover:border-teal-300 hover:bg-teal-50/40 focus:outline-none focus:ring-2 focus:ring-teal-700"
                type="button"
                onClick={() => setDetailKey(item.key)}
              >
                <div className="text-2xl font-semibold text-teal-700">{item.value}</div>
                <div className="mt-1 text-sm text-stone-500">{item.label}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
      <MemoryDetailDialog memory={memory} detailKey={detailKey} onOpenChange={(open) => !open && setDetailKey(null)} />
    </>
  );
}

function MemoryDetailDialog({
  memory,
  detailKey,
  onOpenChange,
}: {
  memory: StoryMemory | null;
  detailKey: MemoryDetailKey | null;
  onOpenChange: (open: boolean) => void;
}) {
  const titles: Record<MemoryDetailKey, string> = {
    chapter_plan: '章节计划',
    chapter_summaries: '章节归档',
    characters: '角色记录',
    foreshadowing: '伏笔记录',
    timeline: '时间线',
    plot_threads: '主线/支线/悬念线',
  };

  return (
    <Dialog open={!!detailKey} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">{detailKey ? titles[detailKey] : '故事记忆'}</DialogTitle>
          <DialogDescription className="text-sm text-stone-500">当前项目故事记忆内容</DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[74vh]">
          <div className="grid gap-3 pr-3">{detailKey ? renderMemoryDetail(memory, detailKey) : null}</div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function renderMemoryDetail(memory: StoryMemory | null, detailKey: MemoryDetailKey) {
  if (detailKey === 'chapter_plan') {
    return renderChapterPlan(memory?.chapter_plan);
  }
  if (detailKey === 'chapter_summaries') {
    return renderRecordList(memory?.chapter_summaries ?? [], '暂无章节归档。', (item, index) => {
      const record = asRecord(item);
      return (
        <DetailItemCard
          key={index}
          title={`第${stringValue(record.chapter_number) || index + 1}章`}
          subtitle={stringValue(record.summary)}
          rows={[
            ['实际事件', joinDisplayList(record.actual_events)],
            ['涉及角色', joinDisplayList(record.involved_characters)],
            ['地点', joinDisplayList(record.locations)],
            ['剧情线', joinDisplayList(record.plot_threads)],
            ['伏笔', joinDisplayList(record.foreshadowing)],
            ['标签', joinDisplayList(record.tags)],
          ]}
        />
      );
    });
  }
  if (detailKey === 'characters') {
    return renderRecordList(arrayValue(memory?.characters?.characters), '暂无角色记录。', (item, index) => {
      const record = asRecord(item);
      return (
        <DetailItemCard
          key={index}
          title={stringValue(record.name) || `角色 ${index + 1}`}
          subtitle={stringValue(record.summary) || stringValue(record.notes) || stringValue(record.note)}
          rows={recordRows(record, ['name', 'summary', 'notes', 'note'])}
        />
      );
    });
  }
  if (detailKey === 'foreshadowing') {
    return renderRecordList(arrayValue(memory?.foreshadowing?.items), '暂无伏笔记录。', (item, index) => {
      const record = asRecord(item);
      const title = stringValue(record.name) || stringValue(record.element) || `伏笔 ${index + 1}`;
      const subtitle = stringValue(record.detail) || stringValue(record.summary);
      return (
        <DetailItemCard
          key={index}
          title={title}
          subtitle={subtitle}
          rows={recordRows(record, ['name', 'element', 'detail', 'summary'])}
        />
      );
    });
  }
  if (detailKey === 'timeline') {
    return renderRecordList(arrayValue(memory?.timeline?.events), '暂无时间线记录。', (item, index) => {
      const record = asRecord(item);
      return (
        <DetailItemCard
          key={index}
          title={stringValue(record.event) || stringValue(record.summary) || `事件 ${index + 1}`}
          subtitle={stringValue(record.detail) || stringValue(record.last_update)}
          rows={recordRows(record, ['event', 'summary', 'detail', 'last_update'])}
        />
      );
    });
  }
  return renderRecordList(arrayValue(memory?.plot_threads?.threads), '暂无主线/支线/悬念线记录。', (item, index) => {
    const record = asRecord(item);
    return (
      <DetailItemCard
        key={index}
        title={stringValue(record.name) || `剧情线 ${index + 1}`}
        subtitle={stringValue(record.last_update) || stringValue(record.summary) || stringValue(record.detail)}
        rows={recordRows(record, ['name', 'last_update', 'summary', 'detail'])}
      />
    );
  });
}

function renderChapterPlan(chapterPlan: StoryMemory['chapter_plan']) {
  const chapters = chapterPlan?.planned_chapters ?? [];
  const volumes = chapterPlan?.volume_plan ?? [];
  if (!chapters.length) {
    return <EmptyPanel text="暂无章节计划。" />;
  }
  if (volumes.length) {
    const groups = groupChaptersByVolume(chapters, volumes);
    return (
      <>
        <div className="grid gap-3">
          {groups.map((group) => (
            <section key={group.key} className="grid gap-3">
              <div className="sticky top-0 z-10 border-b border-stone-200 bg-white/95 py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="text-sm font-semibold text-stone-950">{group.label}</div>
                  {group.volume.range ? <div className="text-xs font-medium text-stone-500">{group.volume.range}章</div> : null}
                </div>
                {group.volume.focus ? <p className="mt-1 text-xs leading-5 text-stone-500">{group.volume.focus}</p> : null}
              </div>
              <div className="grid gap-3">
                {group.chapters.map((chapter, index) => renderChapterCard(chapter, index, false))}
              </div>
            </section>
          ))}
        </div>
      </>
    );
  }
  return chapters.map((chapter, index) => renderChapterCard(chapter, index));
}

function renderChapterCard(chapter: ChapterPlanItem, index: number, showVolume = true) {
  const volumeName = chapter.volume_name || chapter.volume || '';
  return (
    <DetailItemCard
      key={chapter.chapter_number ?? index}
      title={`第${chapter.chapter_number ?? index + 1}章${chapter.title ? `：${chapter.title}` : ''}`}
      subtitle={chapter.goal || '暂无章节目标。'}
      rows={[
        ['分卷', showVolume ? volumeName : ''],
        ['章末期待', chapter.expected_hook || ''],
      ]}
    />
  );
}

function groupChaptersByVolume(chapters: ChapterPlanItem[], volumes: VolumePlanItem[]) {
  const groups = volumes.map((volume, index) => ({
    key: String(volume.volume_number ?? index + 1),
    label: volumeLabel(volume, index),
    volume,
    chapters: chapters.filter((chapter) => chapterBelongsToVolume(chapter, volume, index, volumes)),
  }));
  const groupedNumbers = new Set(groups.flatMap((group) => group.chapters.map((chapter) => chapter.chapter_number)));
  const ungrouped = chapters.filter((chapter) => !groupedNumbers.has(chapter.chapter_number));
  if (ungrouped.length) {
    groups.push({ key: 'ungrouped', label: '未分卷章节', volume: {}, chapters: ungrouped });
  }
  return groups.filter((group) => group.chapters.length);
}

function chapterBelongsToVolume(chapter: ChapterPlanItem, volume: VolumePlanItem, index: number, volumes: VolumePlanItem[]) {
  const volumeNumber = volume.volume_number ?? index + 1;
  if (chapterVolumeNumber(chapter, volumes) === volumeNumber) {
    return true;
  }
  const chapterNumber = chapter.chapter_number;
  if (typeof chapterNumber !== 'number' || !volume.range) {
    return false;
  }
  const range = parseChapterRange(volume.range);
  return !!range && chapterNumber >= range.start && chapterNumber <= range.end;
}

function chapterVolumeNumber(chapter: ChapterPlanItem, volumes: VolumePlanItem[]) {
  if (typeof chapter.volume_number === 'number') {
    return chapter.volume_number;
  }
  const matched = volumes.find((volume) => chapter.volume_name === volume.name || chapter.volume === volume.name);
  return matched?.volume_number;
}

function volumeForChapter(chapter: ChapterPlanItem, volumes: VolumePlanItem[]) {
  const explicitNumber = chapter.volume_number;
  if (typeof explicitNumber === 'number') {
    const matched = volumes.find((volume) => volume.volume_number === explicitNumber);
    if (matched) {
      return matched;
    }
  }
  const explicitName = chapter.volume_name || chapter.volume;
  if (explicitName) {
    const matched = volumes.find((volume) => explicitName === volume.name);
    if (matched) {
      return matched;
    }
  }
  const chapterNumber = chapter.chapter_number;
  if (typeof chapterNumber !== 'number') {
    return undefined;
  }
  return volumes.find((volume) => {
    if (!volume.range) {
      return false;
    }
    const range = parseChapterRange(volume.range);
    return !!range && chapterNumber >= range.start && chapterNumber <= range.end;
  });
}

function parseChapterRange(range: string) {
  const match = range.match(/第?\s*(\d+)\s*章?\s*[-到至~—－]\s*第?\s*(\d+)\s*章?/);
  if (!match) {
    return null;
  }
  return { start: Number(match[1]), end: Number(match[2]) };
}

function volumeLabel(volume: VolumePlanItem, index: number) {
  const number = volume.volume_number ?? index + 1;
  const name = stripVolumePrefix(volume.name || '');
  return name ? `第${number}卷-${name}` : `第${number}卷`;
}

function stripVolumePrefix(value: string) {
  return value.replace(/^第\s*[\d一二三四五六七八九十百零〇]+\s*卷[:：\-\s]*/, '').trim();
}

function renderRecordList<T>(items: T[], emptyText: string, renderItem: (item: T, index: number) => ReactNode) {
  if (!items.length) {
    return <EmptyPanel text={emptyText} />;
  }
  return items.map(renderItem);
}

function DetailItemCard({ title, subtitle, rows }: { title: string; subtitle?: string; rows: Array<[string, string]> }) {
  const visibleRows = rows.filter(([, value]) => value);
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-base font-semibold text-stone-950">{title}</div>
        {subtitle ? <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-stone-700">{subtitle}</p> : null}
        {visibleRows.length ? (
          <div className="mt-3 grid gap-2">
            {visibleRows.map(([label, value]) => (
              <InfoLine key={label} label={label} value={value} />
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SystemConfigPanel({ config }: { config: SystemConfig | null }) {
  const items = [
    ['PROVIDER', config?.provider || '-'],
    ['模型', config?.compat_model || '-'],
    ['调试', config ? (config.llm_trace ? '开启' : '关闭') : '-'],
    ['超时', config ? `${config.llm_timeout_seconds}s` : '-'],
  ];
  return (
    <Card className="bg-stone-50">
      <CardHeader className="p-3 pb-2">
        <CardTitle className="text-sm">系统环境变量</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 p-3 pt-0">
        {items.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[56px_minmax(0,1fr)] gap-2 text-xs">
            <span className="text-stone-500">{label}</span>
            <span className="truncate text-right font-medium text-stone-800" title={value}>
              {value}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ReportsPanel({ reports }: { reports: Record<string, unknown> }) {
  const evalReport = asRecord(reports.chapter_eval_report);
  const scores = asRecord(evalReport.scores);
  const scoreItems = Object.entries(scores).filter(([, value]) => typeof value === 'number');
  const reportCards = [
    ['连续性检查', asRecord(reports.continuity_report)],
    ['章节安全检查', asRecord(reports.chapter_safety_report)],
    ['最终安全检查', asRecord(reports.final_safety_report)],
    ['记忆校验', asRecord(reports.memory_validation_report)],
  ];

  return (
    <ScrollArea className="h-[74vh]">
      <div className="grid gap-4 pr-3">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>章节体验评估</CardTitle>
              <StatusBadge value={stringValue(evalReport.overall_status) || 'unknown'} />
            </div>
            <p className="text-sm text-stone-500">正文长度：{numberValue(evalReport.length) ?? '-'}</p>
          </CardHeader>
          <CardContent>
            {scoreItems.length ? (
              <div className="grid grid-cols-5 gap-3 max-xl:grid-cols-3 max-md:grid-cols-1">
                {scoreItems.map(([key, value]) => (
                  <ScoreMeter key={key} label={reportLabel(key)} value={value as number} />
                ))}
              </div>
            ) : (
              <EmptyPanel text="暂无评分数据。" />
            )}
            <ListBlock className="mt-4" title="编辑备注" items={arrayValue(evalReport.notes)} />
          </CardContent>
        </Card>

        <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
          {reportCards.map(([title, report]) => (
            <ReportCard key={title as string} title={title as string} report={report as Record<string, unknown>} />
          ))}
        </div>
      </div>
    </ScrollArea>
  );
}

function ReportCard({ title, report }: { title: string; report: Record<string, unknown> }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{title}</CardTitle>
          <StatusBadge value={stringValue(report.status) || 'unknown'} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ListBlock title="问题" items={arrayValue(report.issues)} emptyText="未发现明确问题。" />
        <ListBlock title="检查项" items={arrayValue(report.checks)} emptyText="暂无检查项。" />
        {stringValue(report.notes) ? <InfoLine label="备注" value={stringValue(report.notes)} /> : null}
      </CardContent>
    </Card>
  );
}

function MemoryUpdatePanel(props: { archive: Record<string, unknown> | undefined; memoryUpdate: unknown }) {
  const archive = asRecord(props.archive);
  const update = asRecord(props.memoryUpdate);
  const summary = stringValue(update.chapter_summary) || stringValue(archive.summary);

  return (
    <ScrollArea className="h-[74vh]">
      <div className="grid gap-4 pr-3">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle>章节归档</CardTitle>
              <span className="rounded-md bg-stone-100 px-2 py-1 text-sm text-stone-600">
                第{stringValue(archive.chapter_number) || stringValue(update.chapter_number) || '-'}章
              </span>
            </div>
          </CardHeader>
          <CardContent className="grid gap-3">
            <InfoLine label="章节摘要" value={summary || '暂无章节摘要。'} />
            <OptionalListBlock title="实际事件" items={arrayValue(archive.actual_events)} />
            <OptionalListBlock title="涉及角色" items={arrayValue(archive.involved_characters)} />
            <OptionalListBlock title="地点" items={arrayValue(archive.locations)} />
            <OptionalTagBlock title="标签" items={arrayValue(archive.tags)} />
          </CardContent>
        </Card>

        <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
          <UpdateCard title="时间线更新" items={arrayValue(update.timeline_updates)} />
          <UpdateCard title="角色更新" items={arrayValue(update.character_updates)} />
          <UpdateCard title="主线更新" items={arrayValue(update.plot_thread_updates)} />
          <UpdateCard title="伏笔更新" items={arrayValue(update.foreshadowing_updates)} />
          <UpdateCard title="未解问题" items={arrayValue(update.open_questions)} />
          <UpdateCard title="下一章钩子" items={arrayValue(update.next_chapter_hooks)} />
        </div>
      </div>
    </ScrollArea>
  );
}

function UpdateCard({ title, items }: { title: string; items: unknown[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ListBlock title="" items={items} emptyText="暂无更新。" />
      </CardContent>
    </Card>
  );
}

function OptionalListBlock({ title, items }: { title: string; items: unknown[] }) {
  if (!items.length) {
    return null;
  }
  return <ListBlock title={title} items={items} />;
}

function OptionalTagBlock({ title, items }: { title: string; items: unknown[] }) {
  if (!items.length) {
    return null;
  }
  return <TagBlock title={title} items={items} />;
}

function ScoreMeter({ label, value }: { label: string; value: number }) {
  const percent = Math.max(0, Math.min(100, value * 10));
  return (
    <div className="rounded-md border border-stone-200 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-stone-600">{label}</span>
        <strong className="text-xl text-teal-700">{value}</strong>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-100">
        <div className="h-full rounded-full bg-teal-700" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const styles = normalized.includes('pass') || normalized.includes('safe') || normalized.includes('ready')
    ? 'bg-emerald-50 text-emerald-700'
    : normalized.includes('fix') || normalized.includes('review') || normalized.includes('transform')
      ? 'bg-amber-50 text-amber-700'
      : normalized.includes('block')
        ? 'bg-red-50 text-red-700'
        : 'bg-stone-100 text-stone-600';
  return <span className={`rounded-md px-2 py-1 text-xs font-medium ${styles}`}>{value}</span>;
}

function ListBlock({
  title,
  items,
  emptyText = '暂无内容。',
  className = '',
}: {
  title: string;
  items: unknown[];
  emptyText?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      {title ? <h4 className="mb-2 text-sm font-semibold text-stone-700">{title}</h4> : null}
      {items.length ? (
        <div className="grid gap-2">
          {items.map((item, index) => (
            <div key={index} className="min-w-0 rounded-md bg-stone-50 px-3 py-2 text-sm leading-6 text-stone-700">
              <StructuredValue value={item} />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-stone-500">{emptyText}</p>
      )}
    </div>
  );
}

function StructuredValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <div className="grid gap-1">
        {value.map((item, index) => (
          <StructuredValue key={index} value={item} />
        ))}
      </div>
    );
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item !== undefined && item !== null && item !== '');
    if (!entries.length) {
      return <span className="break-words">暂无内容。</span>;
    }
    return (
      <div className="grid min-w-0 gap-1">
        {entries.map(([key, item]) => (
          <div key={key} className="grid min-w-0 grid-cols-[minmax(120px,0.22fr)_minmax(0,1fr)] gap-3 max-sm:grid-cols-1">
            <span className="min-w-0 break-words text-xs leading-6 text-stone-500">{reportLabel(key)}</span>
            <div className="min-w-0 whitespace-pre-wrap break-words text-stone-800">
              <StructuredValue value={item} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return <span className="whitespace-pre-wrap break-words">{displayValue(value)}</span>;
}

function TagBlock({ title, items }: { title: string; items: unknown[] }) {
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-stone-700">{title}</h4>
      {items.length ? (
        <div className="flex flex-wrap gap-2">
          {items.map((item, index) => (
            <span key={index} className="rounded-md bg-teal-50 px-2 py-1 text-sm text-teal-700">
              {displayValue(item)}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-stone-500">暂无标签。</p>
      )}
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-stone-50 px-3 py-2">
      <div className="mb-1 text-xs text-stone-500">{label}</div>
      <div className="whitespace-pre-wrap break-words text-sm leading-6 text-stone-800">{value}</div>
    </div>
  );
}

function MemoBlock({ title, value }: { title: string; value?: string }) {
  return (
    <div className="rounded-md border border-stone-200 p-3">
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      <ScrollArea className="h-44">
        <p className="whitespace-pre-wrap pr-3 text-sm leading-6 text-stone-600">{value?.trim() || '暂无内容。'}</p>
      </ScrollArea>
    </div>
  );
}

function TextViewer({ value, compact = false }: { value: string; compact?: boolean }) {
  return (
    <ScrollArea className={compact ? 'h-[62vh]' : 'h-[74vh]'}>
      <pre className="whitespace-pre-wrap rounded-md bg-stone-50 p-4 text-sm leading-7 text-stone-800">
        {restoreLiteralNewlines(value)}
      </pre>
    </ScrollArea>
  );
}

function JsonViewer({ value }: { value: unknown }) {
  return <TextViewer value={JSON.stringify(value, null, 2)} />;
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-8 text-stone-500">{text}</div>;
}

function chapterPrompt(chapter: ChapterPlanItem, targetWordsPerChapter?: number): string {
  const number = chapter.chapter_number ? `第${chapter.chapter_number}章` : '下一章';
  const title = chapter.title ? `《${chapter.title}》` : '';
  const parts = [`${number}${title}，按照本项目章节计划开始写作。`];
  const targetWords = chapter.target_words || targetWordsPerChapter;
  if (targetWords) {
    parts.push(`本章目标字数：约${targetWords}字。`);
  }
  if (chapter.goal) {
    parts.push(`本章目标：${chapter.goal}`);
  }
  if (chapter.expected_hook) {
    parts.push(`章末期待：${chapter.expected_hook}`);
  }
  return parts.join('\n');
}

function generatedChapterNumbers(memory: StoryMemory | null, runs: RunSummary[]): Set<number> {
  const numbers = new Set<number>();
  memory?.chapter_summaries?.forEach((item) => {
    const value = item.chapter_number;
    if (typeof value === 'number') {
      numbers.add(value);
    }
  });
  runs.forEach((run) => {
    if (typeof run.chapter_number === 'number') {
      numbers.add(run.chapter_number);
    }
  });
  return numbers;
}

function finalizedChapterNumbers(runs: RunSummary[]): Set<number> {
  const finalized = new Set<number>();
  const seen = new Set<number>();
  runs.forEach((run) => {
    if (typeof run.chapter_number !== 'number' || seen.has(run.chapter_number)) {
      return;
    }
    seen.add(run.chapter_number);
    if (run.finalized) {
      finalized.add(run.chapter_number);
    }
  });
  return finalized;
}

function chapterVersions(result: Record<string, unknown> | undefined): Array<{ label: string; value: string }> {
  if (!result) {
    return [];
  }
  const candidates = [
    ['合并初稿', 'merged_chapter'],
    ['连续性修复后', 'continuity_fixed_chapter'],
    ['安全修复后', 'safety_fixed_chapter'],
    ['润色后', 'polished_chapter'],
    ['最终正文', 'final_chapter'],
  ];
  const seen = new Set<string>();
  const versions: Array<{ label: string; value: string }> = [];
  candidates.forEach(([label, key]) => {
    const value = getString(result, key).trim();
    if (value && !seen.has(value)) {
      seen.add(value);
      versions.push({ label, value });
    }
  });
  return versions;
}

function pickJson(source: Record<string, unknown> | undefined, keys: string[]): Record<string, unknown> {
  if (!source) {
    return {};
  }
  return Object.fromEntries(keys.map((key) => [key, source[key]]).filter(([, value]) => value !== undefined));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayValue(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  if (value === undefined || value === null || value === '') {
    return [];
  }
  return [value];
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

function stringValue(value: unknown): string {
  if (typeof value === 'string') {
    return translatedEnumValue(value);
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return '';
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') {
    return translatedEnumValue(value);
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const priority = [
      'event',
      'summary',
      'detail',
      'last_update',
      'note',
      'notes',
      'name',
      'status',
      'source',
      'chapter_number',
    ];
    const parts = priority
      .filter((key) => record[key] !== undefined && record[key] !== '')
      .map((key) => `${reportLabel(key)}：${displayValue(record[key])}`);
    if (parts.length) {
      return parts.join('；');
    }
  }
  return JSON.stringify(value);
}

function restoreLiteralNewlines(value: string): string {
  return value.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n').replace(/\\"/g, '"');
}

function translatedEnumValue(value: string): string {
  const labels: Record<string, string> = {
    main_plot: '主线',
    secondary_plot: '支线',
    subplot: '支线',
    suspense_line: '悬念线',
    suspense: '悬念线',
    mystery_line: '悬念线',
    investigation: '调查线',
    surveillance: '监视线',
    conflict: '冲突',
    conflict_line: '冲突线',
    romance_line: '感情线',
    character_arc: '角色成长线',
    action_taken: '采取行动',
    ability_confirmation: '能力确认',
    physical_change: '身体变化',
    psychological_state: '心理状态',
    relationship_change: '关系变化',
    planned: '计划中',
    active: '进行中',
    activated: '已激活',
    pending: '待推进',
    resolved: '已解决',
    closed: '已关闭',
  };
  return labels[value] ?? value;
}

function joinDisplayList(value: unknown): string {
  const items = arrayValue(value).map(displayValue).filter(Boolean);
  return items.join('\n');
}

function recordRows(record: Record<string, unknown>, excludedKeys: string[]): Array<[string, string]> {
  const excluded = new Set(excludedKeys);
  return Object.entries(record)
    .filter(([key, value]) => !excluded.has(key) && value !== undefined && value !== null && value !== '')
    .map(([key, value]) => [reportLabel(key), Array.isArray(value) ? joinDisplayList(value) : displayValue(value)]);
}

function reportLabel(key: string): string {
  const labels: Record<string, string> = {
    dramatic_task: '戏剧任务',
    continuity: '连续性',
    reader_hook: '读者钩子',
    narrative_texture: '叙事质感',
    colloquial_style: '口语自然度',
    event: '事件',
    summary: '摘要',
    detail: '详情',
    last_update: '更新',
    note: '备注',
    notes: '备注',
    name: '名称',
    role: '角色定位',
    identity: '身份',
    traits: '性格特征',
    motivation: '动机',
    flaw: '弱点',
    threat_level: '威胁等级',
    function: '叙事作用',
    status: '状态',
    source: '来源',
    chapter_number: '章节',
    issue: '问题',
    check: '检查',
    description: '说明',
    reason: '原因',
    evidence: '依据',
    suggestion: '建议',
    action: '动作',
    impact: '影响',
    location: '地点',
    character: '角色',
    relationship: '关系',
    conflict: '冲突',
    status_after: '更新后状态',
    next_chapter_hook: '下一章钩子',
    time: '时间',
    time_marker: '时间',
    significance: '意义',
    update_type: '更新类型',
    thread_name: '线索名称',
    thread_id: '线索标识',
    implication: '暗示',
    payoff: '回收方式',
    element: '元素',
    progress: '进展',
    new_elements: '新增元素',
    hook: '钩子',
    hook_type: '钩子类型',
    next_chapter_promise: '下一章承诺',
    actual_events: '实际事件',
    involved_characters: '涉及角色',
    locations: '地点',
    plot_threads: '剧情线',
    foreshadowing: '伏笔',
    tags: '标签',
    character_ooc: '角色是否 OOC',
    time_location_conflict: '时间地点冲突',
    info_boundary: '信息边界',
    hook_connection: '钩子承接',
  };
  return labels[key] ?? key;
}

function getString(source: Record<string, unknown> | undefined, key: string): string {
  const value = source?.[key];
  return typeof value === 'string' ? value : '';
}

function projectRoot(project: Project | null): string {
  if (!project) {
    return 'projects/{当前小说}';
  }
  return `projects/${project.id}`;
}

function arrayCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes <= 0) {
    return `${rest}s`;
  }
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

function eventLabel(event: { type: string; label: string }): string {
  if (event.type === 'step_started') {
    return `${event.label} 开始`;
  }
  if (event.type === 'step_completed') {
    return `${event.label} 完成`;
  }
  return event.label;
}
