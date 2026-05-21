**一、结构说明**

文件是一个JSON数组，每个对象都严格遵循以下四个字段的结构：



·**CWE\_ID** : 对应的CWE (通用弱点枚举) 条目编号。CISQ规则直接映射到CWE，确保了标准的一致性。



·**Characteristic** : 规则所属的质量标准。涵盖CISQ的四类规则：

"Security" (安全性) 检测可能导致攻击者利用的漏洞。

"Reliability" (可靠性) 检测可能导致程序崩溃、挂起或进入不可预测状态的问题。

"Performance Efficiency" (性能效率) 检测可能导致响应缓慢或资源浪费的低效模式。

"Maintainability" (可维护性)  检测导致代码难以理解、修改或扩展的设计问题。



·**Description**: 对该CWE规则要检测的问题的简要描述。



·**Refactor\_Advice**: 针对该问题给出的具体、可执行的修复或重构建议。



**二、统计**

**总条目数：214条**

**不重复 CWE 数量：138条**

**按维度统计：**

Name                   Count

\----                   -----

Maintainability           48

Performance Efficiency    18

Reliability               74

Security                  74

