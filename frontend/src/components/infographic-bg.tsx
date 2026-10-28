import React, { useState, useEffect } from 'react';

interface SlideData {
  id: number;
  trigger: {
    avatarType: 'woman' | 'man1' | 'man2';
    source: string;
    user: string;
    time: string;
    message: string;
    label: string;
    toastStyle: { top: string; left: string };
    triggerStyle: { top: string; left: string };
  };
  functionTag: {
    label: string;
    style: { top: string; left: string };
  };
  beamPath: string; // SVG path connecting Trigger -> Action/Function -> Output in 1200x650 coordinate space
  code: Array<{ text: string; type?: 'kw' | 'str' | 'comment' | 'fn' | 'plain' }>;
  tags: Array<{ text: string; top: string; left?: string; right?: string }>;
  output: {
    x: number;
    y: number;
  };
  outputNodes: Array<{ x: number; y: number; label: string }>;
  outputLines: Array<[number, number]>;
}

const SLIDES: SlideData[] = [
  // Slide 1: Content Agent Translation Flow (Screenshot 1)
  {
    id: 0,
    trigger: {
      avatarType: 'woman',
      source: 'Sanity Studio',
      user: '@Content Agent',
      time: 'Just now',
      message: '@Content Agent translate the documents mentioned above',
      label: 'TRIGGER',
      toastStyle: { top: '10%', left: '8%' },
      triggerStyle: { top: '28%', left: '52%' },
    },
    functionTag: {
      label: 'AGENT ACTION',
      style: { top: '61%', left: '46%' },
    },
    beamPath: 'M 255 195 L 515 410 L 730 205',
    code: [
      { text: "import {documentEventHandler} from '@sanity/functions'", type: 'kw' },
      { text: "import {createClient} from '@sanity/client'", type: 'kw' },
      { text: '', type: 'plain' },
      { text: "const FROM_LANGUAGE = {id: 'en-US', title: 'English'}", type: 'plain' },
      { text: "const TO_LANGUAGE = {id: 'nb-NO', title: 'Norwegian Bokmål'}", type: 'plain' },
      { text: "const SCHEMA_ID = 'your-schema-id' // from sanity schema list", type: 'comment' },
      { text: '', type: 'plain' },
      { text: 'export const handler = documentEventHandler(async ({context, event}) => {', type: 'fn' },
      { text: '  const {data} = event', type: 'plain' },
      { text: '  const client = createClient({', type: 'plain' },
      { text: "    ...context.clientOptions, apiVersion: 'vX',", type: 'plain' },
      { text: '  })', type: 'plain' },
      { text: '  // drive a stable target ID so re-publishes update same translation', type: 'comment' },
      { text: '  const targetId = `${data._id}-${TO_LANGUAGE.id}`', type: 'str' },
      { text: '  try {', type: 'kw' },
      { text: '    await client.agent.action.translate({', type: 'fn' },
      { text: '      schemaId: SCHEMA_ID, documentId: data._id, async: true,', type: 'plain' },
      { text: "      fromLanguage: FROM_LANGUAGE, toLanguage: TO_LANGUAGE, languageFieldPath: 'language',", type: 'plain' },
      { text: "      targetDocument: { operation: 'createOrReplace', _id: targetId },", type: 'str' },
      { text: '    })', type: 'plain' },
      { text: '  }', type: 'kw' },
      { text: '})', type: 'fn' },
    ],
    tags: [
      { text: '▪ WINTER COLLECTIONS', top: '24%', left: '48%' },
      { text: '▪ WINTER JACKETS', top: '38%', left: '14%' },
    ],
    output: { x: 730, y: 205 },
    outputNodes: [
      { x: 130, y: 75, label: 'DEBUGGING API REQUESTS' },
      { x: 260, y: 92, label: 'TECHNICAL GUIDES' },
      { x: 335, y: 135, label: 'WEBHOOKS' },
      { x: 105, y: 130, label: 'RATE LIMITS' },
      { x: 285, y: 180, label: 'MANAGING API' },
      { x: 70, y: 280, label: 'HELP CENTER ARTICLES' },
      { x: 190, y: 275, label: 'CHANGING NOTIFICATION SETTINGS' },
      { x: 40, y: 360, label: 'METADATA' },
    ],
    outputLines: [
      [0, 1], [1, 2], [0, 3], [1, 4], [3, 5], [5, 6], [5, 7]
    ],
  },
  // Slide 2: Slack Campaign Agent Flow (Screenshot 2)
  {
    id: 1,
    trigger: {
      avatarType: 'man1',
      source: 'Slack @Billy',
      user: '@Sanity',
      time: 'Just now',
      message: '@Sanity Update the holiday campaign with the new sneakers',
      label: 'TRIGGER',
      toastStyle: { top: '18%', left: '10%' },
      triggerStyle: { top: '35%', left: '55%' },
    },
    functionTag: {
      label: 'FUNCTION',
      style: { top: '69%', left: '50%' },
    },
    beamPath: 'M 270 235 L 540 455 L 780 240',
    code: [
      { text: "import {httpRequestHandler} from '@sanity/functions'", type: 'kw' },
      { text: "import {createContentAgent} from 'content-agent'", type: 'kw' },
      { text: "import {generateText} from 'ai'", type: 'kw' },
      { text: '', type: 'plain' },
      { text: 'const contentAgent = createContentAgent({', type: 'plain' },
      { text: '  projectId: process.env.SANITY_ORG_ID, token: process.env.SANITY_TOKEN,', type: 'str' },
      { text: '})', type: 'plain' },
      { text: '', type: 'plain' },
      { text: 'export const handler = httpRequestHandler(async ({request, context}) => {', type: 'fn' },
      { text: '  const form = await request.formData()', type: 'plain' },
      { text: "  const query = form.get('text') as string", type: 'str' },
      { text: "  const channelName = form.get('channel_name') as string", type: 'str' },
      { text: '  // Thread scoped to channel keeps conversation context', type: 'comment' },
      { text: '  const model = contentAgent.agent(threadId, {', type: 'plain' },
      { text: "    instruction: 'Answer questions about content. Be concise.',", type: 'str' },
      { text: '    capabilities: {read: true, write: false},', type: 'plain' },
      { text: '  })', type: 'plain' },
      { text: '  const {text} = await generateText({model, prompt: query})', type: 'fn' },
      { text: '})', type: 'fn' },
    ],
    tags: [
      { text: '▪ SLACK CONTEXT', top: '21%', left: '14%' },
      { text: '▪ WINTER COLLECTIONS', top: '32%', left: '42%' },
    ],
    output: { x: 780, y: 240 },
    outputNodes: [
      { x: 50, y: 120, label: 'LP PROMO BLOCK' },
      { x: 175, y: 195, label: 'CAMPAIGN ASSETS' },
      { x: 265, y: 195, label: 'HERO BANNER' },
      { x: 330, y: 175, label: 'PRODUCT' },
      { x: 375, y: 165, label: 'AX8' },
      { x: 280, y: 245, label: 'QX-2' },
      { x: 310, y: 350, label: 'DROP ANNOUNCEMENT' },
      { x: 230, y: 385, label: 'MARKETING EMAILS' },
      { x: 130, y: 300, label: 'LAST CHANCE' },
      { x: 135, y: 440, label: 'REMINDER' },
    ],
    outputLines: [
      [0, 1], [1, 2], [2, 3], [3, 4], [3, 5], [1, 8], [8, 7], [7, 6], [7, 9]
    ],
  },
  // Slide 3: Webhook Storefront Product Publishing (Screenshot 3)
  {
    id: 2,
    trigger: {
      avatarType: 'man2',
      source: 'Sanity Studio',
      user: '@Jason',
      time: 'Just now',
      message: '@Jason published a new product: ST07 Winter Jacket',
      label: 'TRIGGER',
      toastStyle: { top: '56%', left: '10%' },
      triggerStyle: { top: '74%', left: '40%' },
    },
    functionTag: {
      label: 'FUNCTION',
      style: { top: '37%', left: '46%' },
    },
    beamPath: 'M 220 480 L 510 245 L 720 465',
    code: [
      { text: "import {documentEventHandler} from '@sanity/functions'", type: 'kw' },
      { text: "import {createClient} from '@sanity/client'", type: 'kw' },
      { text: '', type: 'plain' },
      { text: 'const STOREFRONT_WEBHOOK = process.env.STOREFRONT_WEBHOOK_URL', type: 'str' },
      { text: '', type: 'plain' },
      { text: 'export const handler = documentEventHandler(async ({context, event}) => {', type: 'fn' },
      { text: '  const {data} = event', type: 'plain' },
      { text: '  if (!STOREFRONT_WEBHOOK) {', type: 'kw' },
      { text: "    console.error('Storefront webhook URL not found in environment')", type: 'comment' },
      { text: '    return', type: 'kw' },
      { text: '  }', type: 'plain' },
      { text: "  const client = createClient({apiVersion: '2025-06-01'})", type: 'plain' },
      { text: '  // Find every document that references the published product', type: 'comment' },
      { text: "  const referencing = await client.fetch('*[references($id)]', {id: data._id})", type: 'fn' },
      { text: '  if (!referencing.length) {', type: 'kw' },
      { text: "    console.log(`No references found for ${data._id}`)", type: 'comment' },
      { text: '    return', type: 'kw' },
      { text: '  }', type: 'plain' },
      { text: '})', type: 'fn' },
    ],
    tags: [
      { text: '▪ LOOK UP ALL BLOG POSTS', top: '22%', left: '25%' },
      { text: '▪ LOOK UP ALL PRODUCTS', top: '29%', left: '16%' },
      { text: '▪ FOCUS ON CONTENT FROM THE LAST 2 WEEKS', top: '51%', left: '26%' },
    ],
    output: { x: 720, y: 465 },
    outputNodes: [
      { x: 310, y: 75, label: 'SOMETHING ELSE' },
      { x: 190, y: 185, label: 'UPDATE PRODUCTS' },
      { x: 335, y: 195, label: 'UPDATE CATEGORIES' },
      { x: 380, y: 220, label: 'BAGS' },
      { x: 295, y: 235, label: 'SHOES' },
      { x: 260, y: 215, label: 'NB322' },
      { x: 190, y: 310, label: 'UPDATE BLOGS' },
      { x: 265, y: 345, label: 'BLOG POST 1' },
      { x: 145, y: 395, label: 'BLOG POST 2' },
      { x: 165, y: 165, label: 'BLOG POST 3' },
      { x: 75, y: 445, label: 'N3900-22' },
    ],
    outputLines: [
      [0, 2], [1, 2], [2, 3], [2, 4], [1, 5], [1, 6], [6, 7], [6, 8], [1, 9], [8, 10]
    ],
  },
];

export function InfographicBackground() {
  const [slideIndex, setSlideIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setSlideIndex((prev) => (prev + 1) % SLIDES.length);
    }, 7500);
    return () => clearInterval(timer);
  }, []);

  const slide = SLIDES[slideIndex];

  return (
    <div className="landing-infographic-container" aria-hidden="true">
      {/* Background Matrix Dot Coordinate Grid */}
      <div className="landing-infographic-grid" />

      {/* 3-Column Visual Layout (Trigger -> Code Function -> Output DAG Network) */}
      <div className="landing-infographic-stage">
        {/* ========================================================
            COLUMN 1 (LEFT): Event Trigger Card & Coordinate Markers
            ======================================================== */}
        <div className="infographic-col infographic-col-left">
          {/* Subtle cross grid markers */}
          <div className="infographic-cross-grid">
            {Array.from({ length: 24 }).map((_, i) => (
              <span key={i} className="infographic-cross">+</span>
            ))}
          </div>

          {/* Context tags */}
          {slide.tags.map((tag, i) => (
            <span
              key={i}
              className="infographic-context-tag"
              style={{ top: tag.top, left: tag.left, right: tag.right }}
            >
              {tag.text}
            </span>
          ))}

          {/* Floating Trigger Notification Card */}
          <div className="infographic-toast-card" style={slide.trigger.toastStyle}>
            <div className="infographic-toast-header">
              <div className="infographic-avatar">
                {slide.trigger.avatarType === 'woman' ? (
                  <svg viewBox="0 0 32 32" fill="none" className="avatar-svg">
                    <circle cx="16" cy="16" r="16" fill="#1e293b" />
                    <circle cx="16" cy="12" r="6" fill="#cbd5e1" />
                    <path d="M7 27c0-5 4-8 9-8s9 3 9 8" fill="#cbd5e1" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 32 32" fill="none" className="avatar-svg">
                    <circle cx="16" cy="16" r="16" fill="#0f172a" />
                    <circle cx="16" cy="13" r="5.5" fill="#e2e8f0" />
                    <path d="M8 28c0-4.5 3.5-7.5 8-7.5s8 3 8 7.5" fill="#e2e8f0" />
                  </svg>
                )}
                <span className="avatar-arrow">↑</span>
              </div>
              <div className="infographic-toast-meta">
                <span className="toast-source">{slide.trigger.source}</span>
                <span className="toast-time">{slide.trigger.time}</span>
              </div>
            </div>
            <div className="infographic-toast-body">
              <span className="toast-user">{slide.trigger.user}</span>{' '}
              <span className="toast-msg">
                {slide.trigger.message.replace(slide.trigger.user, '').trim()}
              </span>
            </div>
          </div>

          {/* Trigger point and label */}
          <div className="infographic-trigger-anchor" style={slide.trigger.triggerStyle}>
            <span className="trigger-label">{slide.trigger.label}</span>
            <span className="trigger-box" />
          </div>
        </div>

        {/* ========================================================
            COLUMN 2 (MIDDLE): Code Matrix & Function Action Tag
            ======================================================== */}
        <div className="infographic-col infographic-col-center">
          <div className="infographic-code-window">
            {slide.code.map((line, idx) => (
              <div key={idx} className={`infographic-code-line type-${line.type || 'plain'}`}>
                {line.text}
              </div>
            ))}
          </div>

          {/* Central Function/Agent Action Tag */}
          <div className="infographic-action-tag" style={slide.functionTag.style}>
            <span className="action-tag-box" />
            <span className="action-tag-text">{slide.functionTag.label}</span>
          </div>
        </div>

        {/* ========================================================
            COLUMN 3 (RIGHT): Knowledge DAG Network & Output Root
            ======================================================== */}
        <div className="infographic-col infographic-col-right">
          {/* Background dot coordinates */}
          <div className="infographic-cross-grid right-grid">
            {Array.from({ length: 24 }).map((_, i) => (
              <span key={i} className="infographic-dot">•</span>
            ))}
          </div>

          {/* SVG Network Graph */}
          <svg className="infographic-graph-svg" viewBox="0 0 420 520" fill="none">
            {/* Output Node Position */}
            {(() => {
              const rootX = slide.id === 2 ? 30 : 25;
              const rootY = slide.id === 2 ? 395 : 210;

              return (
                <>
                  {/* Radiating lines from Output root */}
                  {slide.outputNodes.map((node, i) => (
                    <line
                      key={`line-out-${i}`}
                      x1={rootX}
                      y1={rootY}
                      x2={node.x}
                      y2={node.y}
                      stroke="rgba(255, 255, 255, 0.22)"
                      strokeWidth="1"
                    />
                  ))}

                  {/* Inter-node DAG connections */}
                  {slide.outputLines.map(([fromIdx, toIdx], i) => {
                    const from = slide.outputNodes[fromIdx];
                    const to = slide.outputNodes[toIdx];
                    if (!from || !to) return null;
                    return (
                      <line
                        key={`line-inter-${i}`}
                        x1={from.x}
                        y1={from.y}
                        x2={nodeSafe(to).x}
                        y2={nodeSafe(to).y}
                        stroke="rgba(255, 255, 255, 0.16)"
                        strokeWidth="1"
                        strokeDasharray="2 3"
                      />
                    );
                  })}

                  {/* Orange Output Root Node */}
                  <rect x={rootX - 6} y={rootY - 6} width="12" height="12" fill="#FF3E00" />
                  <text
                    x={rootX + 12}
                    y={rootY + 4}
                    fill="#ffffff"
                    fontSize="11"
                    fontWeight="700"
                    letterSpacing="0.08em"
                    fontFamily="monospace"
                  >
                    OUTPUT
                  </text>
                </>
              );
            })()}

            {/* Connected Leaf Nodes */}
            {slide.outputNodes.map((node, i) => (
              <g key={`node-${i}`} className="graph-node-group">
                <rect x={node.x - 2.5} y={node.y - 2.5} width="5" height="5" fill="rgba(255, 255, 255, 0.65)" />
                <text
                  x={node.x + 8}
                  y={node.y + 3.5}
                  fill="rgba(255, 255, 255, 0.6)"
                  fontSize="9.5"
                  fontWeight="600"
                  fontFamily="monospace"
                  letterSpacing="0.06em"
                >
                  {node.label}
                </text>
              </g>
            ))}
          </svg>

          {/* Micro Footer link in bottom right */}
          <div className="infographic-micro-learn">
            <span>LEARN MORE →</span>
          </div>
        </div>
      </div>

      {/* ========================================================
          ANIMATED DATA BEAM CONNECTING: TRIGGER -> FUNCTION -> OUTPUT
          ======================================================== */}
      <svg className="infographic-beam-svg" viewBox="0 0 1000 650" preserveAspectRatio="none">
        {/* Dynamic laser connecting the three stages */}
        <path
          d={slide.beamPath}
          stroke="rgba(255, 255, 255, 0.7)"
          strokeWidth="1.5"
          fill="none"
        />
        <path
          d={slide.beamPath}
          stroke="#FF3E00"
          strokeWidth="2.5"
          fill="none"
          strokeDasharray="14 18"
          className="infographic-beam-pulse"
        />
        {/* Moving data packet */}
        <circle key={slideIndex} r="4.5" fill="#FF3E00" className="infographic-beam-particle">
          <animateMotion
            path={slide.beamPath}
            dur="3.0s"
            repeatCount="indefinite"
          />
        </circle>
      </svg>

      {/* Subtle Slide Carousel Indicators */}
      <div className="infographic-slide-indicator">
        {SLIDES.map((_, i) => (
          <span
            key={i}
            className={`slide-indicator-dot ${i === slideIndex ? 'active' : ''}`}
            onClick={() => setSlideIndex(i)}
            title={`Slide ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}

function nodeSafe(node: { x: number; y: number; label: string } | undefined) {
  return node || { x: 0, y: 0, label: '' };
}
