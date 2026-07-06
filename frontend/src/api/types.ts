export type HealthResponse = {
  status: string
  db: string
  hermes: {
    runs_api: string
  }
  version: string
}
