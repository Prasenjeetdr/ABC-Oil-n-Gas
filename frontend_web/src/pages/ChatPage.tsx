'use client';
import React from 'react';
import { useParams } from 'react-router-dom';
import { v4 as uuid } from 'uuid';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Chat,
  useChatScroll,
  useChatContext,
  ChatMessages,
  ChatProgress,
  ChatTextInput,
  ChatError,
  ChatMessageMemo,
  StepEvent,
  ThinkingEvent,
  ChatProvider,
  StartNewChat,
} from '@/components/block/chat';
import {
  isErrorStateEvent,
  isMessageStateEvent,
  isStepStateEvent,
  isThinkingEvent,
} from '@/components/block/chat/types';
import { type MessageResponse } from '@/api/chat/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useMainLayout } from '@/components/block/chat/main-layout-context';
import { FleetMapPanel } from '@/components/drilling/FleetMapPanel';

const initialMessages: MessageResponse[] = [
  {
    id: uuid(),
    role: 'assistant',
    content: {
      format: 2,
      parts: [
        {
          type: 'text',
          text: 'I\'m the Watcher for GUY-001 through GUY-004. Ask "What\'s the fleet doing?" for a status table, or ask about a single well.',
        },
      ],
    },
    createdAt: new Date(),
    type: 'initial',
  },
];

export function ChatImplementation({ chatId }: { chatId: string }) {
  const {
    sendTextMessage,
    userInput,
    setUserInput,
    combinedEvents,
    progress,
    deleteProgress,
    isLoadingHistory,
    isAgentRunning,
  } = useChatContext();

  const { scrollContainerRef, onChatScroll } = useChatScroll({
    chatId,
    events: combinedEvents,
  });

  return (
    <div className="flex size-full min-w-0 flex-col">
      {/* Fleet map on top. It needs an explicit height or Leaflet renders nothing. */}
      <div className="h-[42vh] min-h-[280px] w-full min-w-0 shrink-0 border-b border-border">
        <FleetMapPanel />
      </div>

      {/* Chat full width beneath. flex-1 min-h-0 so the scroll area can shrink. */}
      <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
        <Chat initialMessages={initialMessages}>
          <ScrollArea
            className="mb-5 min-h-0 w-full min-w-0 flex-1"
            scrollViewportRef={scrollContainerRef}
            onWheel={onChatScroll}
          >
            <div className="w-full min-w-0 justify-self-center">
              <ChatMessages isLoading={isLoadingHistory} messages={combinedEvents} chatId={chatId}>
                {combinedEvents &&
                  combinedEvents.map(m => {
                    if (isErrorStateEvent(m)) {
                      return <ChatError key={m.value.id} {...m.value} />;
                    }
                    if (isMessageStateEvent(m)) {
                      return <ChatMessageMemo key={m.value.id} {...m.value} />;
                    }
                    if (isStepStateEvent(m)) {
                      return <StepEvent key={m.value.id} {...m.value} />;
                    }
                    if (isThinkingEvent(m)) {
                      return <ThinkingEvent key={m.type} />;
                    }
                  })}
              </ChatMessages>
              <ChatProgress progress={progress || {}} deleteProgress={deleteProgress} />
            </div>
          </ScrollArea>

          <ChatTextInput
            userInput={userInput}
            setUserInput={setUserInput}
            onSubmit={sendTextMessage}
            runningAgent={isAgentRunning}
          />
        </Chat>
      </div>
    </div>
  );
}

export const ChatPage: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();
  const { hasChat, isNewChat, isLoadingChats, addChatHandler, refetchChats } = useMainLayout();

  if (!chatId) {
    return null;
  }

  if (isLoadingChats) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-4 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (!hasChat) {
    return <StartNewChat createChat={addChatHandler} />;
  }

  return (
    <ChatProvider
      chatId={chatId}
      runInBackground={true}
      isNewChat={isNewChat}
      refetchChats={refetchChats}
    >
      <ChatImplementation chatId={chatId} />
    </ChatProvider>
  );
};
