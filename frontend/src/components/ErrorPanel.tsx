interface ErrorPanelProps {
  message: string;
  onRetry?: () => void;
}

const ErrorPanel = ({ message, onRetry }: ErrorPanelProps) => {
  return (
    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-background/80">
      <div className="bg-card border rounded-lg px-6 py-5 max-w-sm text-center">
        <div className="w-3 h-3 rounded-full bg-destructive mx-auto mb-3" />
        <p className="text-sm font-mono text-foreground mb-1">Connection Error</p>
        <p className="text-xs text-muted-foreground mb-4">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-4 py-1.5 text-xs font-mono bg-card border rounded hover:bg-muted transition-colors text-foreground"
          >
            RETRY
          </button>
        )}
      </div>
    </div>
  );
};

export default ErrorPanel;
