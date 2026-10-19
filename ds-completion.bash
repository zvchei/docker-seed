# Bash completion for ds.py (and the ds shell function).
# Source this file from ~/.bashrc or ~/.bash_aliases.

_DS_PY="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/ds.py"

_ds_services() {
    "$_DS_PY" list 2>/dev/null
}

_ds() {
    # Treat "service:<name>" as one word; ':' is in COMP_WORDBREAKS by default.
    local cur cword words
    if declare -F _get_comp_words_by_ref >/dev/null; then
        _get_comp_words_by_ref -n : cur cword words
    else
        cur=${COMP_WORDS[COMP_CWORD]} cword=$COMP_CWORD words=("${COMP_WORDS[@]}")
    fi
    local COMP_CWORD=$cword COMP_WORDS=("${words[@]}")

    if ((COMP_CWORD == 1)); then
        mapfile -t COMPREPLY < <(compgen -W "run up shell list add add-template new extend" -- "$cur")
        return
    fi

    case ${COMP_WORDS[1]} in
        run|up)
            if ((COMP_CWORD == 2)); then
                mapfile -t COMPREPLY < <(compgen -W "$(_ds_services)" -- "$cur")
            fi
            ;;
        add)
            if ((COMP_CWORD == 2)); then
                mapfile -t COMPREPLY < <(compgen -W "$("$_DS_PY" add 2>/dev/null)" -- "$cur")
            fi
            ;;
        add-template)
            if ((COMP_CWORD == 2)); then
                mapfile -t COMPREPLY < <(compgen -W "$("$_DS_PY" add-template 2>/dev/null)" -- "$cur")
            elif ((COMP_CWORD == 3)); then
                mapfile -t COMPREPLY < <(compgen -W "$("$_DS_PY" add-template "${COMP_WORDS[2]}" 2>/dev/null)" -- "$cur")
                # Bash replaces only the part after the last ':'; drop what it keeps.
                if [[ $COMP_WORDBREAKS == *:* && $cur == *:* ]]; then
                    local prefix=${cur%"${cur##*:}"}
                    COMPREPLY=("${COMPREPLY[@]#"$prefix"}")
                fi
            fi
            ;;
        new)
            # The new service's name comes first; references follow.
            if ((COMP_CWORD >= 3)); then
                mapfile -t COMPREPLY < <(compgen -W "$("$_DS_PY" new 2>/dev/null)" -- "$cur")
                if [[ $COMP_WORDBREAKS == *:* && $cur == *:* ]]; then
                    local prefix=${cur%"${cur##*:}"}
                    COMPREPLY=("${COMPREPLY[@]#"$prefix"}")
                fi
            fi
            ;;
        extend)
            if [[ ${COMP_WORDS[COMP_CWORD - 1]} == --command ]]; then
                mapfile -t COMPREPLY < <(compgen -c -- "$cur")
                return
            fi
            # Count positional arguments before the cursor, skipping --command and its value.
            local i positional=()
            for ((i = 2; i < COMP_CWORD; i++)); do
                case ${COMP_WORDS[i]} in
                    --command) ((i++)) ;;
                    --command=*) ;;
                    *) positional+=("${COMP_WORDS[i]}") ;;
                esac
            done
            case ${#positional[@]} in
                0) mapfile -t COMPREPLY < <(compgen -W "$("$_DS_PY" extend 2>/dev/null)" -- "$cur") ;;
                1) COMPREPLY=() ;;  # the new service's name
                2) mapfile -t COMPREPLY < <(compgen -W "--command $("$_DS_PY" extend "${positional[0]}" 2>/dev/null)" -- "$cur") ;;
                *) mapfile -t COMPREPLY < <(compgen -W "--command" -- "$cur") ;;
            esac
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
