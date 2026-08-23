const main = async () => {
    const query = prompt(">>> ");

    const response = await fetch("http://localhost:11434/api/chat", {
        method: "POST",

        headers: {
            "Content-Type": "application/json",
        },

        body: JSON.stringify({
            model: "qwen3:8b",
            stream: true,
            messages: [{ role: "user", content: query }],
        }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();

        if (done) {
            break;
        }

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");

        // Keep potentially incomplete line for next chunk
        buffer = lines.pop();

        for (const line of lines) {
            if (!line.trim()) continue;

            const data = JSON.parse(line);

            if (data.done) {
                break;
            }

            const content = data.message?.content ?? "";

            Deno.stdout.write(
                new TextEncoder().encode(content),
            );
        }
    }

    console.log();
    main();
};

await main();
