# Source this before any pdd command: `source scripts/pdd-env.sh`
# Headless/non-interactive PDD configuration.
# Recipe taken from PDD's own pdd/ci_drift_heal.py::_build_ci_env().

source ~/.pdd/api-env.zsh          # ANTHROPIC_API_KEY

export PDD_FORCE_LOCAL=1           # THE critical one: local mode reads API keys
                                   # from env. Cloud mode wants interactive
                                   # GitHub SSO, which cannot work headless.
export PDD_FORCE=1                 # skip overwrite AND api-key prompts
export PDD_NO_INTERACTIVE=1
export CI=1
export NO_COLOR=1
export PDD_SKIP_LOCAL_MODELS=1
export PDD_NO_GITHUB_STATE=1
export PDD_RESTORE_PROTECTED_PATHS_ON_FAILURE=1
