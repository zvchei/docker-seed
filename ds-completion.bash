# Bash completion for ds.py (and the ds shell function).
# Source this file from ~/.bashrc or ~/.bash_aliases.

_DS_PY="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/ds.py"

_ds_services() {
    "$_DS_PY" list 2>/dev/null
}

_ds() {
    local cur=${COMP_WORDS[COMP_CWORD]}
    if ((COMP_CWORD == 1)); then
        mapfile -t COMPREPLY < <(compgen -W "run up shell list" -- "$cur")
        return
    fi

    case ${COMP_WORDS[1]} in
        run|up)
            if ((COMP_CWORD == 2)); then
                mapfile -t COMPREPLY < <(compgen -W "$(_ds_services)" -- "$cur")
            fi
            ;;
        shell)
            # Skip leading --serve flags to find the service name's position.
            local i flags=0
            for ((i = 2; i < COMP_CWORD; i++)); do
                case ${COMP_WORDS[i]} in
                    --serve) ((flags++)) ;;
                    *) break ;;
                esac
            done
            local pos=$((COMP_CWORD - 2 - flags))
            if ((pos == 0)); then
                mapfile -t COMPREPLY < <(compgen -W "--serve $(_ds_services)" -- "$cur")
            elif ((pos == 1)); then
                # The command to run in place of the service's own.
                mapfile -t COMPREPLY < <(compgen -c -- "$cur")
            fi
            ;;
    esac
}

complete -o default -F _ds ds ds.py
