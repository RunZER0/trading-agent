import { Routes, Route, NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Signal,
  Bot,
  Briefcase,
  ShieldAlert,
  BarChart3,
  FlaskConical,
  Database,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Signals from './pages/Signals';
import Agent from './pages/Agent';
import Portfolio from './pages/Portfolio';
import RiskSettings from './pages/RiskSettings';
import MarketData from './pages/MarketData';
import Backtest from './pages/Backtest';
import DataManager from './pages/DataManager';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/signals', icon: Signal, label: 'Signals' },
  { to: '/agent', icon: Bot, label: 'Agent' },
  { to: '/portfolio', icon: Briefcase, label: 'Portfolio' },
  { to: '/risk', icon: ShieldAlert, label: 'Risk' },
  { to: '/market', icon: BarChart3, label: 'Market' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
  { to: '/data', icon: Database, label: 'Data' },
];

export default function App() {
  return (
    <div className="flex h-screen bg-gray-950">
      {/* Sidebar */}
      <nav className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold text-green-400 flex items-center gap-2">
            <Bot size={24} />
            Trading Agent
          </h1>
          <p className="text-xs text-gray-500 mt-1">Autonomous AI Trading</p>
        </div>
        <div className="flex-1 px-3">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 text-sm transition-colors ${
                  isActive
                    ? 'bg-green-500/10 text-green-400'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </div>
        <div className="p-4 border-t border-gray-800">
          <p className="text-xs text-gray-600">v1.0.0 &middot; GPT-5.4 Powered</p>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/risk" element={<RiskSettings />} />
          <Route path="/market" element={<MarketData />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/data" element={<DataManager />} />
        </Routes>
      </main>
    </div>
  );
}
