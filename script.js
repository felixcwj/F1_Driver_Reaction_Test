const lightsContainer = document.querySelector('.lights-container');
const lightPods = document.querySelectorAll('.light-pod');
const actionBtn = document.getElementById('action-btn');
const messageArea = document.getElementById('message-area');
const themeSwitch = document.getElementById('checkbox');
const body = document.body;
// Game States
const STATE = {
    IDLE: 'IDLE',
    WAITING: 'WAITING', // Sequence started, waiting for lights out
    READY: 'READY',     // All lights on, waiting for random delay
    STARTED: 'STARTED', // Lights out, timer running
    ENDED: 'ENDED'      // Result shown
};
let currentState = STATE.IDLE;
let startTime = 0;
let timeoutIds = [];
let randomDelayTimeoutId = null;
// Audio (Optional - can add later, keeping it visual for now as per requirements)

// Theme Toggle
themeSwitch.addEventListener('change', () => {
    body.classList.toggle('night-mode');
});
// Button Handler
actionBtn.addEventListener('click', handleAction);
// Also allow Spacebar
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
        handleAction();
    }
});
function handleAction() {
    switch (currentState) {
        case STATE.IDLE:
        case STATE.ENDED:
            startSequence();
            break;
        case STATE.WAITING:
        case STATE.READY:
            triggerFalseStart();
            break;
        case STATE.STARTED:
            finishRace();
            break;
    }
}

function resetLights() {
    lightPods.forEach(pod => {
        const lights = pod.querySelectorAll('.light');
        lights.forEach(l => l.classList.remove('on'));
    });
}

function setAllLights(on) {
    lightPods.forEach(pod => {
        const lights = pod.querySelectorAll('.light');
        lights.forEach(l => {
            if (on) l.classList.add('on');
            else l.classList.remove('on');
        });
    });
}

function startSequence() {
    // Reset State
    currentState = STATE.WAITING;
    resetLights();
    messageArea.classList.add('hidden');
    messageArea.className = 'message hidden'; // Reset classes
    actionBtn.textContent = 'WAIT...';
    actionBtn.style.backgroundColor = '#555';
    // Clear any existing timeouts
    timeoutIds.forEach(id => clearTimeout(id));
    timeoutIds = [];
    if (randomDelayTimeoutId) clearTimeout(randomDelayTimeoutId);
    // Sequence: 1s interval for each of the 5 pods
    for (let i = 0; i < 5; i++) {
        let id = setTimeout(() => {
            if (currentState !== STATE.WAITING) return; // Guard clause
            const pod = lightPods[i];
            const lights = pod.querySelectorAll('.light');
            lights.forEach(l => l.classList.add('on'));
            
            // If this is the last light (index 4), move to READY state
            if (i === 4) {
                currentState = STATE.READY;
                startRandomDelay();
            }
        }, (i + 1) * 1000);
        timeoutIds.push(id);
    }
}

function startRandomDelay() {
    // Random delay between 0.2s (200ms) and 3.0s (3000ms)
    const delay = Math.floor(Math.random() * 2800) + 200;
    randomDelayTimeoutId = setTimeout(() => {
        if (currentState !== STATE.READY) return;
        go();
    }, delay);
}

function go() {
    setAllLights(false); // LIGHTS OUT
    currentState = STATE.STARTED;
    startTime = performance.now();
    actionBtn.textContent = 'LAUNCH!';
    actionBtn.style.backgroundColor = '#00ff00';
    actionBtn.style.color = '#000';
}

function finishRace() {
    const endTime = performance.now();
    const reactionTime = endTime - startTime;
    currentState = STATE.ENDED;
    
    displayResult(reactionTime);
    resetButton();
}

function triggerFalseStart() {
    // Cancel everything
    timeoutIds.forEach(id => clearTimeout(id));
    if (randomDelayTimeoutId) clearTimeout(randomDelayTimeoutId);
    currentState = STATE.ENDED;
    
    messageArea.textContent = "JUMP START! PENALTY";
    messageArea.className = "message penalty";
    messageArea.classList.remove('hidden');
    // Flash lights to indicate error
    setAllLights(true);
    setTimeout(() => setAllLights(false), 200);
    setTimeout(() => setAllLights(true), 400);
    setTimeout(() => setAllLights(false), 600);
    
    resetButton();
}

function displayResult(time) {
    const formattedTime = time.toFixed(3);
    // 3 decimal places
    messageArea.textContent = ${formattedTime} ms;
    messageArea.className = "message success";
    messageArea.classList.remove('hidden');
}

function resetButton() {
    actionBtn.textContent = 'RESTART';
    actionBtn.style.backgroundColor = '';
    // Reset to default CSS
    actionBtn.style.color = '';
}
