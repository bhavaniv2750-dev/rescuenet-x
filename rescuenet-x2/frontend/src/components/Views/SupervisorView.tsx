import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';
import type { Incident, SupervisorTask } from '../../api/types';
import {
  Bot,
  Play,
  AlertOctagon,
  ShieldCheck,
  GitBranch,
  Cpu,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
} from 'lucide-react';

interface SupervisorViewProps {
  incidents: Incident[];
}

type ExecutionState = 'idle' | 'running' | 'completed' | 'failed' | 'ollama_unavailable' | 'awaiting_approval';

interface OllamaInfo {
  provider: string;
  model: string;
  available: boolean;
  model_installed?: boolean;
  status: string;
  error?: string | null;
}

export const SupervisorView: React.FC<SupervisorViewProps> = ({ incidents }) => {
  const [tasks, setTasks] = useState<SupervisorTask[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [ollamaInfo, setOllamaInfo] = useState<OllamaInfo | null>(null);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>(incidents[0]?.id || 'INC-1042');
  const [taskType, setTaskType] = useState('TRIAGE');
  const [instruction, setInstruction] = useState('Evaluate flood level, find closest boat squad, reserve shelter beds, and prepare evacuation geofence.');
  const [execState, setExecState] = useState<ExecutionState>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [latestTask, setLatestTask] = useState<SupervisorTask | null>(null);

  const fetchTasksAndAgents = async () => {
    try {
      const [tRes, aRes] = await Promise.all([
        api.getSupervisorTasks(),
        api.getAgents(),
      ]);
      setTasks(tRes.items);
      setAgents(aRes.agents || []);
      if (aRes.llm_supervisor) {
        setOllamaInfo(aRes.llm_supervisor);
      }
      if (tRes.items.length > 0 && !latestTask) {
        setLatestTask(tRes.items[0]);
      }
    } catch (err: any) {
      console.error('Failed to fetch tasks/agents:', err);
    }
  };

  useEffect(() => {
    fetchTasksAndAgents();
  }, []);

  const handleRunTriage = async () => {
    setExecState('running');
    setErrorMessage(null);

    try {
      const res = await api.executeSupervisorTriage({
        task_type: taskType,
        incident_id: selectedIncidentId,
        instruction,
      });

      setLatestTask(res);
      if (res.requires_human_approval) {
        setExecState('awaiting_approval');
      } else {
        setExecState('completed');
      }
      await fetchTasksAndAgents();
    } catch (err: any) {
      const msg = err.message || 'Execution failed';
      setErrorMessage(msg);
      if (msg.toLowerCase().includes('ollama') || msg.toLowerCase().includes('connect') || msg.toLowerCase().includes('timeout')) {
        setExecState('ollama_unavailable');
      } else {
        setExecState('failed');
      }
    }
  };

  const handleDecline = async (taskId: string) => {
    const note = window.prompt('Reason for declining this plan (recorded in the audit log):') || undefined;
    try {
      const updated = await api.declineSupervisorTask(taskId, note);
      setLatestTask(updated);
      setExecState('completed');
      await fetchTasksAndAgents();
    } catch (err: any) {
      alert(`Decline failed: ${err.message}`);
    }
  };

  const handleApprove = async (taskId: string) => {
    try {
      const updated = await api.approveSupervisorTask(taskId);
      setLatestTask(updated);
      setExecState('completed');
      await fetchTasksAndAgents();
    } catch (err: any) {
      alert(`Approval failed: ${err.message}`);
    }
  };

  return (
    <div className="supervisor-container">
      <div className="view-header">
        <div>
          <h2>AI Supervisor & Multi-Agent Orchestration</h2>
          <p>
            Local-first LLM reasoning (Ollama Qwen 4B Instruct) orchestrating specialized telemetry,
            geospatial intelligence, squad routing, and medical logistics. The model only advises: a deterministic rule
            (five or more victims, or HIGH/CRITICAL severity) forces commander approval before dispatch.
          </p>
        </div>
      </div>

      {/* Agents Roster Strip */}
      <div className="agents-strip panel">
        <div className="panel-title-bar">
          <div>
            <h3>Active Specialized Sub-Agents</h3>
            <p>RescueNet Multi-Agent Orchestration Engine v2.0</p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {ollamaInfo && (
              <span
                className={`status-pill ${ollamaInfo.available ? 'pill-active' : 'pill-critical'}`}
                title={`Model: ${ollamaInfo.model}`}
              >
                <Cpu size={12} style={{ marginRight: '4px', display: 'inline' }} />
                OLLAMA {ollamaInfo.available ? 'ONLINE' : 'OFFLINE'}: {ollamaInfo.model}
              </span>
            )}
            <span className="status-pill pill-active">
              {agents.length || 6} AGENTS REGISTERED
            </span>
          </div>
        </div>
        <div className="agents-grid">
          {agents.map((ag) => (
            <div key={ag.id} className="agent-box">
              <div className="agent-box-top">
                <span className="agent-icon-symbol font-mono">{ag.icon}</span>
                <span className="agent-status-dot dot-green" />
              </div>
              <div className="agent-box-name">{ag.name}</div>
              <div className="agent-box-role">{ag.role}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="supervisor-main-grid">
        {/* Trigger Orchestration Panel */}
        <div className="panel trigger-card">
          <div className="panel-title-bar">
            <div>
              <h3>Run Supervisor Triage</h3>
              <p>Dispatch the multi-agent swarm to evaluate an incident</p>
            </div>
            <Bot className="text-cyan" size={20} />
          </div>

          <div className="trigger-form">
            <label>
              Select Target Incident
              <select
                className="select-input"
                value={selectedIncidentId}
                onChange={(e) => setSelectedIncidentId(e.target.value)}
              >
                {incidents.slice(0, 15).map((inc) => (
                  <option key={inc.id} value={inc.id}>
                    {inc.id} — {inc.area} ({inc.people_affected} people, {inc.severity})
                  </option>
                ))}
              </select>
            </label>

            <label>
              Mission Directive / Triage Policy
              <select
                className="select-input"
                value={taskType}
                onChange={(e) => setTaskType(e.target.value)}
              >
                <option value="TRIAGE">Comprehensive Tactical Triage (All Agents)</option>
                <option value="RESCUE_DISPATCH">Squad Dispatch & Routing Optimization</option>
                <option value="ALERT_ASSESSMENT">Geotargeted Public Alert Warning Analysis</option>
                <option value="SITUATION_REPORT">Incident Commander Situation Report</option>
              </select>
            </label>

            <label>
              Operational Constraints / Custom Instructions
              <textarea
                rows={2}
                className="text-input"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
            </label>

            <button
              className="btn-primary btn-block"
              style={{ marginTop: '12px' }}
              disabled={execState === 'running'}
              onClick={handleRunTriage}
            >
              {execState === 'running' ? (
                <>
                  <RefreshCw className="animate-spin" size={16} /> Local Ollama Reasoning in Progress...
                </>
              ) : (
                <>
                  <Play size={16} /> Execute Supervisor Swarm
                </>
              )}
            </button>

            {/* Actual Backend Execution State Indicators */}
            {execState === 'running' && (
              <div
                style={{
                  marginTop: '14px',
                  padding: '12px',
                  background: 'rgba(6, 182, 212, 0.08)',
                  border: '1px solid #06b6d4',
                  borderRadius: '6px',
                  color: '#67e8f9',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
                  <RefreshCw className="animate-spin" size={16} /> Running Ollama Inference
                </div>
                <div style={{ marginTop: '4px', fontSize: '12px', color: '#a5f3fc' }}>
                  Sending incident location, nearest available teams and the nearest IndoFloods river gauge to the local Qwen 4B model...
                </div>
              </div>
            )}

            {execState === 'ollama_unavailable' && (
              <div
                style={{
                  marginTop: '14px',
                  padding: '12px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid #ef4444',
                  borderRadius: '6px',
                  color: '#f87171',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
                  <AlertTriangle size={16} /> Ollama Service Unavailable
                </div>
                <div style={{ marginTop: '4px', fontSize: '12px' }}>
                  {errorMessage || 'Local Ollama endpoint unreachable at http://127.0.0.1:11434. Check `ollama list` and background process.'}
                </div>
              </div>
            )}

            {execState === 'failed' && (
              <div
                style={{
                  marginTop: '14px',
                  padding: '12px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid #ef4444',
                  borderRadius: '6px',
                  color: '#f87171',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
                  <AlertOctagon size={16} /> Swarm Execution Failed
                </div>
                <div style={{ marginTop: '4px', fontSize: '12px' }}>{errorMessage}</div>
              </div>
            )}

            {execState === 'awaiting_approval' && (
              <div
                style={{
                  marginTop: '14px',
                  padding: '12px',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid #f59e0b',
                  borderRadius: '6px',
                  color: '#fbbf24',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
                  <AlertTriangle size={16} /> Awaiting Commander Approval
                </div>
                <div style={{ marginTop: '4px', fontSize: '12px' }}>
                  Reasoning complete. High-consequence life-safety dispatch requires manual authorization.
                </div>
              </div>
            )}

            {execState === 'completed' && (
              <div
                style={{
                  marginTop: '14px',
                  padding: '12px',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid #10b981',
                  borderRadius: '6px',
                  color: '#34d399',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
                  <CheckCircle size={16} /> Execution Completed
                </div>
                <div style={{ marginTop: '4px', fontSize: '12px' }}>
                  Advisory triage output confirmed and saved to SQLite audit log.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Triage Decision Output & Human Gatekeeper */}
        <div className="panel decision-card">
          <div className="panel-title-bar">
            <div>
              <h3>Supervisor Decision & Evidence Dossier</h3>
              <p>Task ID: {latestTask?.id || 'TASK-801'}</p>
            </div>
            <GitBranch className="text-emerald" size={20} />
          </div>

          {latestTask ? (
            <div className="decision-content">
              <div className="decision-top-badge">
                <span className="font-mono text-cyan font-bold">{latestTask.task_type}</span>
                <span
                  className={`status-pill ${
                    ['COMPLETED', 'APPROVED'].includes(latestTask.status) ? 'pill-active' : latestTask.status === 'DECLINED' ? 'pill-muted' : 'pill-critical'
                  }`}
                >
                  {latestTask.status}
                </span>
              </div>

              <div className="dossier-section">
                <h4>1. Synthesized Multi-Agent Evidence</h4>
                <div className="dossier-box" style={{ whiteSpace: 'pre-wrap' }}>
                  {latestTask.findings}
                </div>
              </div>

              <div className="dossier-section">
                <h4>2. Tactical Action Recommendations</h4>
                <div className="dossier-box box-accent" style={{ whiteSpace: 'pre-wrap' }}>
                  {latestTask.recommendations}
                </div>
              </div>

              {/* Human Authorization Gatekeeper Section */}
              {latestTask.requires_human_approval && (
                <div className="gatekeeper-box">
                  <div className="gatekeeper-header">
                    <AlertOctagon className="text-red" size={20} />
                    <div>
                      <strong>MANDATORY HUMAN AUTHORIZATION REQUIRED</strong>
                      <p>
                        High-consequence decision involves life safety & evacuation dispatch.
                        Dispatch is blocked until a commander approves.
                      </p>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="btn-primary btn-block"
                      onClick={() => handleApprove(latestTask.id)}
                    >
                      <ShieldCheck size={16} /> Approve & Dispatch
                      {latestTask.suggested_team_id ? ` ${latestTask.suggested_team_id}` : ''}
                    </button>
                    <button className="btn-secondary btn-block" onClick={() => handleDecline(latestTask.id)}>
                      Decline Plan
                    </button>
                  </div>
                </div>
              )}

              {latestTask.status === 'DECLINED' && (
                <div className="approved-dossier-note">
                  ✕ Plan declined by the commander{latestTask.decision_note ? `: ${latestTask.decision_note}` : ''}.
                  {latestTask.incident_id ? ` Incident ${latestTask.incident_id} moved to REJECTED and can be re-queued.` : ''}
                </div>
              )}

              {!latestTask.requires_human_approval && latestTask.approved_by && (
                <div className="approved-dossier-note">
                  ✓ Authorization verified by: <strong>{latestTask.approved_by}</strong> at{' '}
                  {new Date(latestTask.updated_at).toLocaleTimeString()}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-prompt">
              Select an incident and trigger the supervisor swarm to inspect the decision output.
            </div>
          )}
        </div>
      </div>

      {/* Persistent Supervisor Audit Trail */}
      <div className="panel audit-table-panel" style={{ marginTop: '20px' }}>
        <div className="panel-title-bar">
          <div>
            <h3>Supervisor Task History</h3>
            <p>Persistent audit logging stored in SQLite</p>
          </div>
        </div>
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>TASK ID</th>
                <th>DIRECTIVE</th>
                <th>TITLE</th>
                <th>AGENT SWARM FLOW</th>
                <th>APPROVAL GATE</th>
                <th>STATUS</th>
                <th>TIMESTAMP</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id} onClick={() => setLatestTask(t)} style={{ cursor: 'pointer' }}>
                  <td className="font-mono text-cyan font-bold">{t.id}</td>
                  <td>
                    <span className="badge-team">{t.task_type}</span>
                  </td>
                  <td>{t.title}</td>
                  <td className="text-xs text-muted font-mono">{t.agent_flow}</td>
                  <td>
                    {t.requires_human_approval ? (
                      <span className="text-red font-bold text-xs">⚠️ Approval Req</span>
                    ) : (
                      <span className="text-emerald text-xs">✓ Cleared</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`status-pill ${
                        ['COMPLETED', 'APPROVED'].includes(t.status) ? 'pill-active' : t.status === 'DECLINED' ? 'pill-muted' : 'pill-critical'
                      }`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="text-xs text-muted font-mono">
                    {new Date(t.created_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
