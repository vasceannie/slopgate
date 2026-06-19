import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FlagProvider } from "@/context/FlagContext";
import { RulesConfigProvider } from "@/context/RulesConfigContext";
import { TraceDataProvider } from "@/context/TraceDataContext";

const Dashboard = lazy(() => import("./pages/Dashboard.tsx"));
const NotFound = lazy(() => import("./pages/NotFound.tsx"));

const queryClient = new QueryClient();

const ROUTE_LOADING_MESSAGE = "Loading dashboard…";

function RouteLoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">{ROUTE_LOADING_MESSAGE}</div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <TraceDataProvider>
        <RulesConfigProvider>
          <FlagProvider>
            <BrowserRouter>
              <Suspense fallback={<RouteLoadingFallback />}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </FlagProvider>
        </RulesConfigProvider>
      </TraceDataProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
