request(R) :- request_count(R,_).

{ place(R,D,P,W) : candidate_slot(R,D,P,W) } = C :- request_count(R,C).

% Конфликт с базовой занятостью
:- place(R,D,P,W), busy_teacher(D,P,W).
:- place(R,D,P,both), busy_teacher(D,P,num).
:- place(R,D,P,both), busy_teacher(D,P,den).
:- place(R,D,P,num), busy_teacher(D,P,both).
:- place(R,D,P,den), busy_teacher(D,P,both).

% Конфликт с групповой занятостью конкретной заявки
:- place(R,D,P,W), busy_group(R,D,P,W).
:- place(R,D,P,both), busy_group(R,D,P,num).
:- place(R,D,P,both), busy_group(R,D,P,den).
:- place(R,D,P,num), busy_group(R,D,P,both).
:- place(R,D,P,den), busy_group(R,D,P,both).

% ВУЦ
:- place(R,D,P,W), vuc_day(R,D).

% Две консультации одной заявки в один день запрещены
:- place(R,D,P1,W1), place(R,D,P2,W2), P1 != P2.
:- place(R,D,P1,W1), place(R,D,P2,W2), W1 != W2.

% Исключённый день
:- place(R,D,P,W), excluded_day(R,D).

% Глобальный конфликт между заявками преподавателя
:- place(R1,D,P,W), place(R2,D,P,W), R1 != R2.
:- place(R1,D,P,both), place(R2,D,P,num), R1 != R2.
:- place(R1,D,P,both), place(R2,D,P,den), R1 != R2.
:- place(R1,D,P,num), place(R2,D,P,both), R1 != R2.
:- place(R1,D,P,den), place(R2,D,P,both), R1 != R2.

% Мягкие предпочтения

% Не ставить первой парой
:~ place(R,D,1,W), avoid_first_pair(R). [1@5,R,D,W]

% Не ставить последней парой
:~ place(R,D,7,W), avoid_last_pair(R). [1@5,R,D,W]

% Предпочитаемый день
:~ place(R,D,P,W), preferred_day(R,PD), D != PD. [1@6,R,D,P,W] 

% Минимизировать окна / улучшать компактность расписания
:~ place(R,D,P,W), slot_penalty(R,D,P,W,Weight). [Weight@3,R,D,P,W]

#show place/4.