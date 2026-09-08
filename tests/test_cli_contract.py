# tests/test_cli_contract.py
"""
Golden test del contratto CLI di src/main.py (vincolo R3 del refactor
library/CLI, docs/plans/2026-07-08-001-refactor-pge-library-cli-plan.md).

Il contratto e' byte-for-byte: usage string, messaggi di validazione dei
flag, exit code, derivazione del default output, percorso EngineError.
Questi test devono restare verdi INVARIATI per tutte le fasi del refactor:
sono la rete di sicurezza che garantisce che la CLI non cambi mentre
l'orchestrazione migra in api.py e i package vengono rinominati.

Usa la stessa fixture a sys.modules di test_main.py (tests/main_mocks.py).

Il golden si muove solo quando la CLI acquista superficie di proposito --
non durante un refactor, che e' il vincolo che questo file difende. Ultimo
movimento: issue #248, il flag --bw del preset B&W della partitura.
"""

import sys
import pytest
from unittest.mock import patch

from tests.main_mocks import mocks  # noqa: F401  (fixture pytest)


USAGE = (
    "Uso: python main.py <file.yml> [output.aif] "
    "[--visualize] [--show-static] [--show-voice-offsets] "
    "[--plot-envelopes nomi,csv] "
    "[--magnify] [--magnify-at SPEC] "
    "[--page-duration SECONDI] "
    "[--grain-height duration|read-span] "
    "[--bw] "
    "[--per-stream] "
    "[--renderer csound|numpy|supercollider] "
    "[--jobs N|auto] "
    "[--format aiff|wav|flac] "
    "[--samples-dir DIR] [--log-dir DIR] "
    "[--orc-path PATH] [--incdir DIR] [--ssdir DIR] [--sfdir DIR] "
    "[--message-level N] "
    "[--keep-sco] [--sco-dir DIR] "
    "[--sc-synthdef-source PATH] [--sc-synthdef-dir DIR] "
    "[--sc-block-size N] [--sc-max-nodes N] "
    "[--keep-osc] [--osc-dir DIR] "
    "[--cache] [--cache-dir DIR] "
    "[--reaper] [--reaper-path FILE] "
    "[--grain-json] "
    "[--export-sv] [--sv-path FILE] [--sv-layout multi|single]"
)


def _run_expect_exit(mocks, argv, expected_code=1):
    """Esegue main() con argv e verifica SystemExit(expected_code)."""
    with patch.object(sys, 'argv', argv):
        with pytest.raises(SystemExit) as exc_info:
            mocks['main'].main()
    assert exc_info.value.code == expected_code


class TestUsageGolden:
    """Senza argomenti: usage esatta su stdout, exit 1."""

    def test_usage_string_byte_identical(self, mocks, capsys):
        _run_expect_exit(mocks, ['main.py'])
        assert capsys.readouterr().out == USAGE + "\n"


class TestJobsValidationGolden:
    """Messaggi esatti di --jobs (valore non numerico / < 1)."""

    def test_non_numeric_message(self, mocks, capsys):
        _run_expect_exit(mocks, ['main.py', 'test.yml', '--jobs', 'tanti'])
        assert capsys.readouterr().out == (
            "--jobs non valido: 'tanti'. Usa un intero >= 1 oppure 'auto'.\n"
        )

    def test_zero_message(self, mocks, capsys):
        _run_expect_exit(mocks, ['main.py', 'test.yml', '--jobs', '0'])
        assert capsys.readouterr().out == (
            "--jobs deve essere >= 1, ricevuto: 0. "
            "Usa 1 per il rendering sequenziale.\n"
        )

    def test_negative_message(self, mocks, capsys):
        _run_expect_exit(mocks, ['main.py', 'test.yml', '--jobs', '-3'])
        assert capsys.readouterr().out == (
            "--jobs deve essere >= 1, ricevuto: -3. "
            "Usa 1 per il rendering sequenziale.\n"
        )


class TestPageDurationValidationGolden:
    """Messaggi esatti di --page-duration (non numerico / non positivo)."""

    def test_non_numeric_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--page-duration', 'abc'])
        assert capsys.readouterr().out == (
            "--page-duration non valido: 'abc'. Deve essere un numero.\n"
        )

    def test_non_positive_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--page-duration', '-5'])
        assert capsys.readouterr().out == (
            "--page-duration deve essere positivo, ricevuto: -5.0\n"
        )

    def test_zero_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--page-duration', '0'])
        assert capsys.readouterr().out == (
            "--page-duration deve essere positivo, ricevuto: 0.0\n"
        )


class TestPlotEnvelopesValidationGolden:
    """Messaggio esatto per envelope ignoti in --plot-envelopes.

    L'universo dei nomi validi e' quello del mock PLOT_ENVELOPE_KEYS
    (tests/main_mocks.py): {volume, pitch, density, volume_prob}.
    """

    def test_unknown_envelope_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--plot-envelopes', 'bogus'])
        assert capsys.readouterr().out == (
            "Envelope non validi: bogus. "
            "Validi: density, pitch, volume, volume_prob\n"
        )

    def test_unknown_mixed_with_valid_message(self, mocks, capsys):
        _run_expect_exit(
            mocks,
            ['main.py', 'test.yml', '--plot-envelopes', 'volume,bogus,zz'])
        assert capsys.readouterr().out == (
            "Envelope non validi: bogus, zz. "
            "Validi: density, pitch, volume, volume_prob\n"
        )


class TestMagnifyAtValidationGolden:
    """I 4 errori di _parse_magnify_spec + SPEC vuoto, messaggi esatti."""

    def test_invalid_token_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--magnify-at', 'zoom'])
        assert capsys.readouterr().out == (
            "--magnify-at: token non valido 'zoom'. "
            "Usa chiave=valore (es. t=14,zoom=10).\n"
        )

    def test_unknown_key_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--magnify-at', 't=5,foo=1'])
        assert capsys.readouterr().out == (
            "--magnify-at: chiave ignota 'foo'. "
            "Valide: out, src, stream, t, y, zoom.\n"
        )

    def test_non_numeric_value_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--magnify-at', 't=abc'])
        assert capsys.readouterr().out == (
            "--magnify-at: valore non numerico per 't': 'abc'.\n"
        )

    def test_missing_t_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--magnify-at', 'zoom=10'])
        assert capsys.readouterr().out == (
            "--magnify-at: ogni target richiede la chiave 't' "
            "(tempo in secondi).\n"
        )

    def test_empty_spec_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--magnify-at', ';'])
        assert capsys.readouterr().out == (
            "--magnify-at: nessun target valido nello SPEC.\n"
        )


class TestGrainHeightValidationGolden:
    """Messaggio esatto di --grain-height (valore fuori dai due modi)."""

    def test_unknown_mode_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--grain-height', 'banana'])
        assert capsys.readouterr().out == (
            "--grain-height non valido: 'banana'. "
            "Valori: duration, read-span\n")


class TestSvLayoutValidationGolden:
    """Messaggio esatto per --sv-layout non valido."""

    def test_invalid_layout_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--sv-layout', 'bogus'])
        assert capsys.readouterr().out == (
            "--sv-layout non valido: 'bogus'. Valori: multi, single\n"
        )


class TestScBlockSizeValidationGolden:
    """Messaggi esatti di --sc-block-size (valore non numerico / < 1)."""

    def test_non_numeric_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--sc-block-size', 'molti'])
        assert capsys.readouterr().out == (
            "--sc-block-size non valido: 'molti'. Deve essere un intero >= 1.\n"
        )

    def test_zero_message(self, mocks, capsys):
        _run_expect_exit(mocks, ['main.py', 'test.yml', '--sc-block-size', '0'])
        assert capsys.readouterr().out == (
            "--sc-block-size deve essere >= 1, ricevuto: 0\n"
        )


class TestFormatValidationGolden:
    """Messaggio esatto per --format non supportato."""

    def test_unsupported_format_message(self, mocks, capsys):
        _run_expect_exit(
            mocks, ['main.py', 'test.yml', '--format', 'mp3'])
        assert capsys.readouterr().out == (
            "Formato non supportato: 'mp3'. Usa: aiff, wav, flac\n"
        )


class TestDefaultOutputDerivationGolden:
    """Derivazione del default output: output.aif, output.wav, output.flac."""

    def _rendered_output_path(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        return mocks['engine_instance'].render.call_args.kwargs['output_path']

    def test_default_is_output_aif(self, mocks):
        assert self._rendered_output_path(
            mocks, ['main.py', 'test.yml']) == 'output.aif'

    def test_format_wav_derives_output_wav(self, mocks):
        assert self._rendered_output_path(
            mocks, ['main.py', 'test.yml', '--format', 'wav']) == 'output.wav'

    def test_format_flac_derives_output_flac(self, mocks):
        assert self._rendered_output_path(
            mocks,
            ['main.py', 'test.yml', '--format', 'flac']) == 'output.flac'

    def test_explicit_output_wins_over_format(self, mocks):
        assert self._rendered_output_path(
            mocks,
            ['main.py', 'test.yml', 'mio.aif', '--format', 'wav']) == 'mio.aif'


class TestEngineErrorPathGolden:
    """EngineError durante il flusso: user_message() + riga Dettagli + exit 1."""

    def test_engine_error_prints_user_message_and_details(self, mocks, capsys):
        from pge.shared.exceptions import SampleNotFoundError
        err = SampleNotFoundError(filename='pino.wav', search_path='./refs/')
        mocks['generator_instance'].load_yaml.side_effect = err

        _run_expect_exit(mocks, ['main.py', 'test.yml', 'out.aif'])
        out = capsys.readouterr().out
        assert err.user_message() in out
        # Il log path e' quello del mock logger (tests/main_mocks.py)
        assert "  Dettagli:     /tmp/engine.log\n" in out

    def test_file_not_found_message(self, mocks, capsys):
        """Golden mosso dalla #257: il messaggio passa al formato di casa.

        Prima era « Errore: file 'missing.yml' non trovato», stampato dal
        ramo `except FileNotFoundError` che questa issue toglie. Ora lo YAML
        mancante ha un tipo suo e passa dall'handler `EngineError` come ogni
        altro errore di configurazione: `[ERRORE] <head>` piu' contesto, piu'
        la riga «Dettagli:» col log. Il movimento e' di proposito e il
        messaggio migliora (nomina il path assoluto cercato), che e' il
        criterio che la issue pone.
        """
        import os
        from pge.shared.exceptions import ConfigFileNotFoundError

        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))

        _run_expect_exit(mocks, ['main.py', 'missing.yml', 'out.aif'])
        out = capsys.readouterr().out
        assert ("[ERRORE] File di configurazione non trovato: 'missing.yml'\n"
                in out)
        assert f"  Path cercato: {os.path.abspath('missing.yml')}\n" in out
        assert "  Dettagli:     /tmp/engine.log\n" in out

    def test_file_not_found_builtin_non_e_piu_una_diagnosi(self, mocks, capsys):
        """Il rovescio del golden precedente (issue #257).

        Un `FileNotFoundError` nudo che risale dal caricamento non nomina piu'
        lo YAML: cade nel ramo generico. E' cio' che rende la garanzia una
        proprieta' del tipo e non dell'estensione del blocco `try`.
        """
        mocks['generator_instance'].load_yaml.side_effect = FileNotFoundError()

        _run_expect_exit(mocks, ['main.py', 'missing.yml', 'out.aif'])
        out = capsys.readouterr().out
        assert "missing.yml' non trovato" not in out
