# Bash completion for ds.py (and the ds shell function).
# Source this file from ~/.bashrc or ~/.bash_aliases.

_DS_PY="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/ds.py"

_ds_services() {
    "$_DS_PY" list 2>/dev/null
}

_ds() {
    local cur=${COMP_WORDS[COMP_CWORD]}
    case $COMP_CWORD in
        1)
            mapfile -t COMPREPLY < <(compgen -W "r run u up s shell l list" -- "$cur")
            ;;
        2)
            case ${COMP_WORDS[1]} in
                r|run|u|up|s|shell)
                    mapfile -t COMPREPLY < <(compgen -W "$(_ds_services)" -- "$cur")
                    ;;
            esac
            ;;
        3)
            # The command to run in place of the service's own.
            case ${COMP_WORDS[1]} in
                s|shell) mapfile -t COMPREPLY < <(compgen -c -- "$cur") ;;
            esac
            ;;
    esac
}

complete -o default -F _ds ds ds.py
