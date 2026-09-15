import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth, roleHome } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { CelebrateProvider } from './components/ui/Celebrate';
import { AppShell } from './components/Layout/AppShell';
import { clearSession } from './services/session';

// Routes load on demand. Eagerly importing all ten pages pulled Monaco, Recharts and
// every screen into the first download, which a student on a phone connection paid for
// before seeing the login form. Most participants only ever open three of these.
const LandingPage = lazy(() => import('./pages/LandingPage').then((m) => ({ default: m.LandingPage })));
const Login = lazy(() => import('./pages/Login').then((m) => ({ default: m.Login })));
const Register = lazy(() => import('./pages/Register').then((m) => ({ default: m.Register })));
const Workspace = lazy(() => import('./pages/Workspace').then((m) => ({ default: m.Workspace })));
const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })));
const Profile = lazy(() => import('./pages/Profile').then((m) => ({ default: m.Profile })));
const AssessmentPage = lazy(() => import('./pages/AssessmentPage').then((m) => ({ default: m.AssessmentPage })));
const ExpertPortal = lazy(() => import('./pages/ExpertPortal').then((m) => ({ default: m.ExpertPortal })));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard').then((m) => ({ default: m.AdminDashboard })));
const RAGInspector = lazy(() => import('./pages/RAGInspector').then((m) => ({ default: m.RAGInspector })));

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('TRACE Tutor App Error Boundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-950 text-white flex flex-col items-center justify-center p-6 space-y-4 font-sans">
          <div className="bg-red-500/10 border border-red-500/30 p-6 rounded-2xl max-w-lg text-center space-y-3 shadow-2xl">
            <h2 className="text-lg font-extrabold text-red-400">TRACE Tutor System Recovery</h2>
            <p className="text-xs text-slate-300 font-mono leading-relaxed bg-slate-900 p-3 rounded-xl border border-red-500/20">
              {this.state.error?.toString()}
            </p>
            <button
              onClick={() => {
                // Only the session, not every key the app owns: clearing all of storage
                // also threw away the theme and the guest language choice.
                clearSession();
                window.location.href = '/login';
              }}
              className="px-5 py-2.5 bg-red-500 text-white font-extrabold text-xs rounded-xl hover:bg-red-600 transition-all shadow-md shadow-red-500/20"
            >
              Reset Session & Return to Login
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const Splash = () => (
  <div className="min-h-screen bg-surface flex items-center justify-center">
    <div className="flex items-center gap-3 text-primary font-mono text-xs font-bold animate-pulse">
      <img src="/nctb_ict_logo.png" alt="" className="w-8 h-8 object-contain" /> Loading TRACE Tutor...
    </div>
  </div>
);

// Role-based access control: unauthenticated users go to login (and return afterwards), wrong roles go to their own home.
const ProtectedRoute = ({ allowedRoles, children }) => {
  const { user, role, ready } = useAuth() || {};
  const location = useLocation();
  if (!ready) return <Splash />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (allowedRoles && !allowedRoles.includes(role)) return <Navigate to={roleHome(role)} replace />;
  return children;
};

const shell = (page, allowedRoles) => (
  <ProtectedRoute allowedRoles={allowedRoles}>
    <AppShell>{page}</AppShell>
  </ProtectedRoute>
);

export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <CelebrateProvider>
        <AuthProvider>
          <Router>
            <Suspense fallback={<Splash />}>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/onboarding" element={<Navigate to="/register" replace />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />

                <Route path="/dashboard" element={shell(<Dashboard />)} />
                <Route path="/workspace" element={shell(<Workspace />)} />
                <Route path="/profile" element={shell(<Profile />)} />
                <Route path="/assessment" element={shell(<AssessmentPage />, ['STUDENT', 'RESEARCHER_ADMIN'])} />
                <Route path="/expert" element={shell(<ExpertPortal />, ['EXPERT_TEACHER', 'RESEARCHER_ADMIN'])} />
                <Route path="/admin/rag" element={shell(<RAGInspector />, ['RESEARCHER_ADMIN'])} />
                <Route path="/admin" element={shell(<AdminDashboard />, ['RESEARCHER_ADMIN'])} />

                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </Router>
        </AuthProvider>
        </CelebrateProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
