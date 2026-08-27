// =============================================================================
// supercollider/pge_grain.scd
//
// SynthDef del grano per il backend SuperCollider (issue #228).
// E' l'omologo di csound/main.orc: l'unico pezzo di DSP scritto a mano di
// questo backend. Tutto il resto -- score, tabelle, tempi -- lo genera
// Python (src/pge/rendering/sc_score_writer.py).
//
// Uso: e' anche lo script che compila se stesso.
//
//     PGE_SYNTHDEF_DIR=generated sclang supercollider/pge_grain.scd
//
// oppure, dal Makefile:   make sc-synthdef
//
// Su una macchina senza display serve anche QT_QPA_PLATFORM=offscreen:
// sclang e' linkato a Qt e senza un server X aborta (SIGABRT) prima di
// eseguire una riga di questo file. Il target make e il renderer lo
// impostano da soli.
//
// Il .scsyndef prodotto e' un artefatto di build (come un .o): il renderer
// lo ricompila da solo quando manca o quando questo file e' piu' recente.
// sclang serve solo qui, una volta; il rendering vero invoca solo scsynth.
//
// -----------------------------------------------------------------------------
// CORRISPONDENZA CON GLI ALTRI DUE BACKEND
//
//   main.orc (Csound)                     qui
//   -----------------                     ---
//   poscil(aEnv, iFreq, iSampleTable,     BufRd.ar su Phasor.ar
//          iStartNorm)                    (lettura ciclica del buffer)
//   iFreq = iSpeed / iSampleLen           rate * BufRateScale.kr(buf)
//   iStart -> iStartNorm                  startSec * BufSampleRate.kr(buf)
//   poscil(iAmp, 1/p3, iEnvTable)         BufRd.ar su Line.ar(0, N-1, dur)
//   ampdb(iVolume)                        amp, gia' lineare dallo score
//   irad = idegree * PI / 180             panRad, gia' in radianti
//   aMid/aSide, /sqrt(2)                  identico
//
// GrainRenderer (NumPy) e' il riferimento numerico. Due scelte servono a
// stargli accanto e non sono negoziabili senza rompere la parita':
//
// 1. interpolation: 2 (lineare) sulla lettura del sample. NumPy interpola
//    linearmente (`_interpolate_wrapped`); la cubica di poscil3 sarebbe un
//    terzo comportamento.
//
// 2. La finestra e' una TABELLA percorsa da 0 a N-1 nell'arco del grano, non
//    un EnvGen. La registry NumPy genera ogni finestra del catalogo su
//    `linspace(a, b, n)`, cioe' indicizzando k/(n-1): percorrere una tabella
//    di N punti da 0 a N-1 in n campioni da' esattamente gli stessi valori,
//    a meno dell'errore di interpolazione della tabella.
// =============================================================================

(
var dir = "PGE_SYNTHDEF_DIR".getenv ? ".";

SynthDef(\pgeGrain, { |out = 0, buf = 0, envBuf = 1, dur = 0.05,
                      startSec = 0.0, rate = 1.0, amp = 1.0, panRad = 0.0|

    var frames, phase, source, envIndex, env, sig, mid, side;

    // --- lettura del sample -------------------------------------------------
    // Phasor avvolge in [0, frames): e' il `% n_source` del renderer NumPy e
    // il ciclo di poscil sulla tabella Csound. rate negativo (grano al
    // contrario) avvolge all'indietro. BufRateScale compensa un sample rate
    // del file diverso da quello del server, come
    // `pitch_ratio * file_sr / output_sr` in NumPy.
    //
    // ATTENZIONE, e' costato un giro di CI: l'offset di lettura si somma
    // FUORI dal Phasor, non si passa come `resetPos`. resetPos e' il valore a
    // cui saltare quando arriva un trigger; senza trigger il Phasor parte da
    // `start`, cioe' da 0. Passandolo li' ogni grano leggeva dall'inizio del
    // file invece che dalla propria posizione -- un guasto silenzioso, perche'
    // il suono c'e' comunque ed e' solo il materiale sbagliato. Sommandolo
    // qui il risultato non dipende piu' da quale input il costruttore legga.
    frames = BufFrames.kr(buf);
    phase = (
        Phasor.ar(trig: 0, rate: rate * BufRateScale.kr(buf), start: 0, end: frames)
        + (startSec * BufSampleRate.kr(buf))
    ) % frames;
    source = BufRd.ar(1, buf, phase, loop: 1, interpolation: 2);

    // --- finestra -----------------------------------------------------------
    // Una passata sola sulla tabella nell'arco del grano. doneAction: 2
    // libera il nodo quando la finestra e' finita: la durata del grano e'
    // quella della rampa, non serve un /n_free nello score.
    envIndex = Line.ar(0, BufFrames.kr(envBuf) - 1, dur, doneAction: 2);
    env = BufRd.ar(1, envBuf, envIndex, loop: 0, interpolation: 2);

    sig = source * env * amp;

    // --- pan mid/side a potenza costante ------------------------------------
    mid  = sig * cos(panRad);
    side = sig * sin(panRad);
    Out.ar(out, [(mid + side) / 2.sqrt, (mid - side) / 2.sqrt]);

}).writeDefFile(dir);

("[pge] SynthDef pgeGrain scritta in " ++ dir).postln;
0.exit;
)
