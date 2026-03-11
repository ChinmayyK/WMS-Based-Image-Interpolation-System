interface LoadingOverlayProps {
  message?: string;
  progress?: number;
}

const LoadingOverlay = ({ message = "Loading frames…", progress }: LoadingOverlayProps) => {
  return (
    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-background/80">
      {/* Spinner */}
      <div className="w-8 h-8 border-2 border-border border-t-primary rounded-full animate-spin mb-3" />
      <p className="text-xs font-mono text-muted-foreground">{message}</p>
      {progress !== undefined && (
        <div className="mt-2 w-32 h-1 bg-border rounded overflow-hidden">
          <div
            className="h-full bg-primary rounded transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
};

export default LoadingOverlay;
