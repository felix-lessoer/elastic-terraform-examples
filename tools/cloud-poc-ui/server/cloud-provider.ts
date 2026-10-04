export type CloudSlug = 'gcp';

export type GuidedOperation =
  | 'preflight'
  | 'terraform-init'
  | 'terraform-plan'
  | 'terraform-apply'
  | 'discovery'
  | 'analysis'
  | 'workflows'
  | 'final-links';

export type ProgressState =
  | 'queued'
  | 'running'
  | 'validating'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'rolled-back';

export interface ProgressUpdate {
  stage: string;
  message: string;
  percent?: number;
}

export interface ProviderContext {
  write(line: string): void;
  progress(update: ProgressUpdate): Promise<void>;
}

export interface OperationRequest {
  projectId: string;
  confirmation?: string;
  workflowIds?: string[];
}

export interface CredentialStatus {
  elasticConfigured: boolean;
  cloudConfigured: boolean;
  method: 'application-default' | 'impersonation' | 'environment' | 'none';
}

export interface DiscoverySummary {
  manifestVersion: string;
  manifestHash: string;
  resourceCount: number;
  partial: boolean;
  warnings: string[];
}

export interface FinalLinks {
  cockpit?: string;
  cloudConsole: string;
}

export interface CloudProvider {
  readonly slug: CloudSlug;
  readonly displayName: string;
  readonly terraformDirectory: string;
  credentialStatus(): Promise<CredentialStatus>;
  execute(
    operation: GuidedOperation,
    request: OperationRequest,
    context: ProviderContext,
  ): Promise<unknown>;
}
