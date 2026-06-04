import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TraceDataProvider } from "@/context/TraceDataContext";
import { FlagProvider } from "@/context/FlagContext";
import { RulesConfigProvider } from "@/context/RulesConfigContext";
import Dashboard from "./pages/Dashboard.tsx";
import NotFound from "./pages/NotFound.tsx";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <TraceDataProvider>
        <RulesConfigProvider>
        <FlagProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </FlagProvider>
        </RulesConfigProvider>
      </TraceDataProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
