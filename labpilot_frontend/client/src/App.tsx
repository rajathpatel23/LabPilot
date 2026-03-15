// LabPilot App
// Design: Clinical Research Portal — deep navy sidebar, off-white content
// Routes: Home, Conversations, Training, Experiments, Evaluation, Artifacts

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";

import Home from "./pages/Home";
import Conversations from "./pages/Conversations";
import Training from "./pages/Training";
import Experiments from "./pages/Experiments";
import Evaluation from "./pages/Evaluation";
import Artifacts from "./pages/Artifacts";
import InputPage from "./pages/Input";
import NotFound from "./pages/NotFound";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/conversations" component={Conversations} />
      <Route path="/conversations/:id" component={Conversations} />
      <Route path="/training" component={Training} />
      <Route path="/experiments" component={Experiments} />
      <Route path="/experiments/:id" component={Experiments} />
      <Route path="/evaluation" component={Evaluation} />
      <Route path="/input" component={InputPage} />
      <Route path="/artifacts" component={Artifacts} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <TooltipProvider>
          <Toaster position="top-right" />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
