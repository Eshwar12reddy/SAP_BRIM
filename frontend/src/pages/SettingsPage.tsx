import React, { useEffect, useState } from 'react';
import {
  Monitor,
  Moon,
  Sun,
  Brain,
  Trash2,
  Pencil,
  Check,
  X,
  RefreshCw,
  CheckCircle2,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  apiGetMemorySettings,
  apiUpdateMemorySettings,
  apiGetMemories,
  apiUpdateMemory,
  apiDeleteMemory,
  apiDeleteAllMemories,
  apiGetScenarios,
  apiUpdateScenario,
  apiDeleteScenario,
  apiGetCustomInstructions,
  apiUpdateCustomInstructions,
} from '../services/api';
import type { ConversationMemoryItem, ScenarioMemoryItem } from '../types';

type Appearance = 'light' | 'dark' | 'system';

export const SettingsPage: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [appearance, setAppearance] = useState<Appearance>(() => {
    const saved = localStorage.getItem('clyptus-appearance');
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'dark';
  });

  // Memory management state
  const [memoryEnabled, setMemoryEnabled] = useState<boolean>(true);
  const [memories, setMemories] = useState<ConversationMemoryItem[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioMemoryItem[]>([]);
  const [loadingMemories, setLoadingMemories] = useState<boolean>(false);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editMemorySummary, setEditMemorySummary] = useState<string>('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // SAP model & consulting preferences state
  const [sapPrefs, setSapPrefs] = useState<{
    targetEnvironment: 's4hana_cloud' | 's4hana_onprem' | 'ecc_6';
    responseTone: 'technical' | 'balanced' | 'executive';
    diagramsEnabled: boolean;
  }>(() => {
    try {
      const saved = localStorage.getItem('clyptus-sap-preferences');
      if (saved) return JSON.parse(saved);
    } catch {}
    return {
      targetEnvironment: 's4hana_onprem',
      responseTone: 'technical',
      diagramsEnabled: true,
    };
  });

  const updateSapPref = <K extends keyof typeof sapPrefs>(key: K, value: (typeof sapPrefs)[K]) => {
    setSapPrefs((prev) => {
      const next = { ...prev, [key]: value };
      localStorage.setItem('clyptus-sap-preferences', JSON.stringify(next));
      return next;
    });
  };

  // Custom instructions state
  const [aboutUser, setAboutUser] = useState<string>('');
  const [howToRespond, setHowToRespond] = useState<string>('');
  const [isSavingInstructions, setIsSavingInstructions] = useState<boolean>(false);
  const [instructionsSaved, setInstructionsSaved] = useState<boolean>(false);

  const handleSaveInstructions = async () => {
    setIsSavingInstructions(true);
    setInstructionsSaved(false);
    try {
      await apiUpdateCustomInstructions({
        about_user: aboutUser,
        how_to_respond: howToRespond,
      });
      setInstructionsSaved(true);
      setTimeout(() => setInstructionsSaved(false), 3000);
    } catch (e) {
      console.error('Failed to save custom instructions:', e);
    } finally {
      setIsSavingInstructions(false);
    }
  };

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const updateTheme = () =>
      document.documentElement.classList.toggle(
        'dark',
        appearance === 'dark' || (appearance === 'system' && media.matches)
      );
    updateTheme();
    media.addEventListener('change', updateTheme);
    return () => media.removeEventListener('change', updateTheme);
  }, [appearance]);

  const chooseAppearance = (value: Appearance) => {
    setAppearance(value);
    localStorage.setItem('clyptus-appearance', value);
    window.dispatchEvent(new Event('theme-change'));
  };

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  // Load memory data
  const loadMemoryData = async () => {
    setLoadingMemories(true);
    try {
      apiGetCustomInstructions()
        .then((data) => {
          if (data.about_user) setAboutUser(data.about_user);
          if (data.how_to_respond) setHowToRespond(data.how_to_respond);
        })
        .catch(() => {});

      const settings = await apiGetMemorySettings();
      setMemoryEnabled(settings.memory_enabled);
      if (settings.memory_enabled) {
        const memData = await apiGetMemories({ limit: 50 });
        setMemories(memData.items || []);
        const scenData = await apiGetScenarios();
        setScenarios(scenData || []);
      }
    } catch (err) {
      console.error('Failed to load memory settings or data:', err);
    } finally {
      setLoadingMemories(false);
    }
  };

  useEffect(() => {
    loadMemoryData();
  }, []);

  const handleToggleMemory = async () => {
    try {
      const nextVal = !memoryEnabled;
      await apiUpdateMemorySettings(nextVal);
      setMemoryEnabled(nextVal);
      setStatusMessage(nextVal ? 'Memory enabled.' : 'Memory disabled. New chats will not access prior context.');
      setTimeout(() => setStatusMessage(null), 3000);
      if (nextVal) {
        loadMemoryData();
      }
    } catch (err: any) {
      console.error('Failed to toggle memory:', err);
    }
  };

  const handleStartEdit = (item: ConversationMemoryItem) => {
    setEditingMemoryId(item.id);
    setEditMemorySummary(item.summary);
  };

  const handleSaveEdit = async (memoryId: string) => {
    if (!editMemorySummary.trim()) return;
    try {
      await apiUpdateMemory(memoryId, { summary: editMemorySummary.trim() });
      setEditingMemoryId(null);
      loadMemoryData();
      setStatusMessage('Memory record updated.');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update memory:', err);
    }
  };

  const handleDeleteMemory = async (memoryId: string) => {
    try {
      await apiDeleteMemory(memoryId);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
      setStatusMessage('Memory deleted.');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  };

  const handleDeleteAllMemories = async () => {
    if (!window.confirm('Are you sure you want to delete all persistent memory? This cannot be undone.')) {
      return;
    }
    try {
      await apiDeleteAllMemories();
      setMemories([]);
      setScenarios([]);
      setStatusMessage('All personal memories purged successfully.');
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to delete all memories:', err);
    }
  };

  const handleToggleScenarioStatus = async (scenario: ScenarioMemoryItem) => {
    try {
      const nextStatus = scenario.status === 'open' ? 'resolved' : 'open';
      await apiUpdateScenario(scenario.id, { status: nextStatus });
      loadMemoryData();
    } catch (err) {
      console.error('Failed to update scenario status:', err);
    }
  };

  const handleDeleteScenario = async (scenarioId: string) => {
    try {
      await apiDeleteScenario(scenarioId);
      setScenarios((prev) => prev.filter((s) => s.id !== scenarioId));
    } catch (err) {
      console.error('Failed to delete scenario:', err);
    }
  };

  return (
    <section className="workspace-page settings-page">
      <div className="workspace-heading">
        <div>
          <span className="eyebrow">MAKE YOUR SPACE YOURS</span>
          <h1>Settings</h1>
          <p>Manage your account, persistent cross-chat memory, and workspace preferences.</p>
        </div>
      </div>

      {statusMessage && (
        <div className="mb-4 p-3 rounded-xl bg-orange-500/10 border border-orange-500/30 text-xs text-orange-600 dark:text-orange-400 flex items-center gap-2">
          <CheckCircle2 size={16} />
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Account Section */}
      <div className="settings-group">
        <div className="settings-group-heading">
          <h2>Account</h2>
          <p>Your sign-in and account details.</p>
        </div>
        <div className="settings-row">
          <div className="settings-row-icon">
            <span className="account-avatar">
              {user?.name ? user.name.charAt(0).toUpperCase() : 'C'}
            </span>
          </div>
          <div>
            <strong>{user?.name || 'SAP Consultant'}</strong>
            <span>{user?.email || 'Enterprise User'}</span>
          </div>
          <span className="settings-placeholder">Active</span>
        </div>
      </div>

      {/* Cross-Chat Memory Management Section */}
      <div className="settings-group">
        <div className="settings-group-heading">
          <div className="flex items-center gap-2">
            <Brain size={18} className="text-orange-500" />
            <h2>Persistent Cross-Chat Memory</h2>
          </div>
          <p>
            Retain technical SAP scenarios, confirmed findings, and environment preferences across chats with strict per-user privacy.
          </p>
        </div>

        {/* Toggle On / Off */}
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 mb-4 flex items-center justify-between">
          <div className="pr-4">
            <strong className="block text-xs font-semibold text-slate-800 dark:text-slate-200 mb-0.5">
              Cross-Chat Memory
            </strong>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              When active, new chats leverage verified context from your earlier conversations without re-pasting details.
            </p>
          </div>
          <button
            type="button"
            onClick={handleToggleMemory}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              memoryEnabled ? 'bg-orange-500' : 'bg-slate-300 dark:bg-slate-700'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                memoryEnabled ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {memoryEnabled && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                Active Memory Facts ({memories.length})
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={loadMemoryData}
                  disabled={loadingMemories}
                  className="p-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 cursor-pointer"
                  title="Refresh memory list"
                >
                  <RefreshCw size={13} className={loadingMemories ? 'animate-spin' : ''} />
                </button>
                {memories.length > 0 && (
                  <button
                    type="button"
                    onClick={handleDeleteAllMemories}
                    className="button button-outline button-small text-rose-600 border-rose-300 dark:border-rose-800 hover:bg-rose-50 dark:hover:bg-rose-950/40 cursor-pointer"
                  >
                    Clear All Memory
                  </button>
                )}
              </div>
            </div>

            {/* List of Memories */}
            {memories.length === 0 ? (
              <div className="p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-800 text-center text-xs text-slate-500">
                No persistent memories saved yet. Discuss SAP scenarios and findings in chat to establish durable context.
              </div>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {memories.map((mem) => (
                  <div
                    key={mem.id}
                    className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 flex flex-col gap-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                          {mem.memory_type}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                            mem.provenance === 'user_stated'
                              ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
                              : mem.provenance === 'user_confirmed'
                              ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                              : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
                          }`}
                        >
                          {mem.provenance === 'assistant_hypothesis' ? 'AI Hypothesis' : mem.provenance.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        {editingMemoryId === mem.id ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleSaveEdit(mem.id)}
                              className="p-1 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 rounded cursor-pointer"
                              title="Save correction"
                            >
                              <Check size={14} />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingMemoryId(null)}
                              className="p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded cursor-pointer"
                              title="Cancel"
                            >
                              <X size={14} />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => handleStartEdit(mem)}
                              className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded cursor-pointer"
                              title="Edit / Correct memory"
                            >
                              <Pencil size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteMemory(mem.id)}
                              className="p-1 text-slate-400 hover:text-rose-600 rounded cursor-pointer"
                              title="Delete memory"
                            >
                              <Trash2 size={13} />
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {editingMemoryId === mem.id ? (
                      <textarea
                        value={editMemorySummary}
                        onChange={(e) => setEditMemorySummary(e.target.value)}
                        className="w-full text-xs p-2 rounded-lg border border-orange-500 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none"
                        rows={2}
                      />
                    ) : (
                      <p className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                        {mem.summary}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Structured Incident Scenarios */}
            {scenarios.length > 0 && (
              <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
                <span className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-2">
                  Tracked SAP Scenarios &amp; Incidents ({scenarios.length})
                </span>
                <div className="space-y-2">
                  {scenarios.map((scen) => (
                    <div
                      key={scen.id}
                      className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 flex items-center justify-between"
                    >
                      <div className="min-w-0 pr-2">
                        <strong className="block text-xs text-slate-800 dark:text-slate-200 truncate">
                          {scen.scenario_title}
                        </strong>
                        <span className="text-[11px] text-slate-500">
                          Status: <span className="capitalize font-semibold">{scen.status}</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleToggleScenarioStatus(scen)}
                          className="px-2 py-1 rounded text-[10px] font-semibold border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                        >
                          {scen.status === 'open' ? 'Mark Resolved' : 'Reopen'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteScenario(scen.id)}
                          className="p-1 text-slate-400 hover:text-rose-600 rounded cursor-pointer"
                          title="Delete scenario"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* SAP Model & Consulting Preferences Section */}
      <div className="settings-group">
        <div className="settings-group-heading">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white">SAP Consulting &amp; Model Preferences</h2>
          </div>
          <p className="text-xs text-slate-500">Configure target SAP release and architectural consulting response style.</p>
        </div>

        <div className="space-y-4 pt-1">
          {/* Target SAP Environment */}
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Default SAP Target Environment
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {[
                { id: 's4hana_onprem', label: 'S/4HANA On-Premise', sub: '2020 - 2023 / OP' },
                { id: 's4hana_cloud', label: 'S/4HANA Cloud', sub: 'Public / Private Edition' },
                { id: 'ecc_6', label: 'SAP ERP / ECC 6.0', sub: 'Classic ERP & CI/CC' },
              ].map((env) => (
                <button
                  key={env.id}
                  type="button"
                  onClick={() => updateSapPref('targetEnvironment', env.id as any)}
                  className={`p-2.5 rounded-xl border text-left cursor-pointer transition ${
                    sapPrefs.targetEnvironment === env.id
                      ? 'border-[#38BDF8] bg-sky-50/50 dark:bg-sky-950/20 text-[#38BDF8]'
                      : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0b0b12] text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  <div className="text-xs font-semibold">{env.label}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{env.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Response Tone / Detail Level */}
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Consulting Response Tone
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {[
                { id: 'technical', label: 'Technical & Rigorous', sub: 'SPRO paths, DB tables, T-Codes' },
                { id: 'balanced', label: 'Balanced & Consultative', sub: 'Architecture & best practices' },
                { id: 'executive', label: 'Executive Summary', sub: 'High-level business impacts' },
              ].map((tone) => (
                <button
                  key={tone.id}
                  type="button"
                  onClick={() => updateSapPref('responseTone', tone.id as any)}
                  className={`p-2.5 rounded-xl border text-left cursor-pointer transition ${
                    sapPrefs.responseTone === tone.id
                      ? 'border-[#38BDF8] bg-sky-50/50 dark:bg-sky-950/20 text-[#38BDF8]'
                      : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0b0b12] text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  <div className="text-xs font-semibold">{tone.label}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{tone.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Diagram Generation Toggle */}
          <div className="flex items-center justify-between p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#0b0b12]">
            <div>
              <div className="text-xs font-medium text-slate-800 dark:text-slate-200">
                Visual Architecture &amp; Sequence Diagrams
              </div>
              <div className="text-[11px] text-slate-400">
                Render interactive flowcharts and process diagrams when explaining integration flows
              </div>
            </div>
            <button
              type="button"
              onClick={() => updateSapPref('diagramsEnabled', !sapPrefs.diagramsEnabled)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                sapPrefs.diagramsEnabled ? 'bg-[#38BDF8]' : 'bg-slate-300 dark:bg-slate-700'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                  sapPrefs.diagramsEnabled ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* ChatGPT-Grade Custom Instructions Section */}
      <div className="settings-group">
        <div className="settings-group-heading">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-orange-500" />
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Custom Instructions</h2>
          </div>
          <p className="text-xs text-slate-500">Provide standing directives that Clyptus.AI will consider in every response.</p>
        </div>

        <div className="space-y-4 pt-1">
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              What would you like Clyptus.AI to know about you to provide better responses?
            </label>
            <p className="text-[11px] text-slate-400 mb-1.5">
              e.g., "Senior SAP BRIM Architect specializing in Convergent Invoicing, S/4HANA 2023 on-premise, handling high-volume billing."
            </p>
            <textarea
              value={aboutUser}
              onChange={(e) => setAboutUser(e.target.value)}
              placeholder="Your SAP role, active release, modules, and project focus..."
              rows={3}
              className="w-full text-xs p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0b0b12] text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-[#38BDF8] resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              How would you like Clyptus.AI to respond?
            </label>
            <p className="text-[11px] text-slate-400 mb-1.5">
              e.g., "Always include SPRO customizing paths, standard database tables (DFKK*), and numbered steps. Prefer concise architecture diagrams."
            </p>
            <textarea
              value={howToRespond}
              onChange={(e) => setHowToRespond(e.target.value)}
              placeholder="Standing response tone, formatting preferences, and technical expectations..."
              rows={3}
              className="w-full text-xs p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0b0b12] text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-[#38BDF8] resize-none"
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-emerald-500 font-medium">
              {instructionsSaved && "✓ Custom instructions saved successfully."}
            </span>
            <button
              type="button"
              onClick={handleSaveInstructions}
              disabled={isSavingInstructions}
              className="px-4 py-1.5 rounded-xl bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition cursor-pointer"
            >
              {isSavingInstructions ? "Saving..." : "Save Instructions"}
            </button>
          </div>
        </div>
      </div>

      {/* Appearance Section */}
      <div className="settings-group">
        <div className="settings-group-heading">
          <h2>Appearance</h2>
          <p>Choose your preferred interface theme.</p>
        </div>
        <div className="appearance-options">
          {([
            ['light', Sun, 'Light'],
            ['dark', Moon, 'Dark'],
            ['system', Monitor, 'System'],
          ] as const).map(([value, Icon, title]) => (
            <button
              key={value}
              className={`appearance-option cursor-pointer ${appearance === value ? 'selected' : ''}`}
              onClick={() => chooseAppearance(value)}
            >
              <Icon size={17} />
              <span>{title}</span>
              {appearance === value && <i />}
            </button>
          ))}
        </div>
      </div>

      {/* Sign Out Section */}
      <div className="settings-group logout-group">
        <div className="settings-group-heading">
          <h2>Sign out</h2>
          <p>Log out of your current session on this device.</p>
        </div>
        <button
          className="button button-outline button-small cursor-pointer"
          onClick={handleLogout}
        >
          Sign out
        </button>
      </div>
    </section>
  );
};
