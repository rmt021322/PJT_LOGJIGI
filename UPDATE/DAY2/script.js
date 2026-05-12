// 스크립트 숨기기
function hideTitle() {
    let title = document.getElementById("mainTitle")
    title.style.display = "none"
}

// 결과값 비우기
function clearResult() {
    let resultBox = document.getElementById("resultBox")
    resultBox.innerHTML = ""
}

// 이미지 바꾸기
function changeCharacter(imageName) {
    let character = document.getElementById("character")

    // character.src = "/static/character/" + imageName
    character.src = "/static/character/" + imageName + "?v=" + new Date().getTime()
}

// 말풍선 바꾸기
function changeText(message) {
    let sayText = document.getElementById("sayText")

    sayText.innerText = message
}



// 블로그 탐색
function blogSearch() {
    hideTitle()
     clearResult()

    changeCharacter("findinglogs.png")
    changeText("블로그를 탐색 중이에요..")
}

// 웹 탐색
function webSearch() {
    hideTitle()
     clearResult()

    changeCharacter("findingweb.png")
    changeText("인터넷을 검색하고 있어요...")
}

// 추천 받기
function recommendPost() {
    hideTitle()

    changeCharacter("recommending.png")
    changeText("이런 글들을 추천해요!")

    let resultBox = document.getElementById("resultBox")

    resultBox.innerHTML = `
        <h3>게시글 보러 가기</h3>
        <a href="#">하나둘셋넷</a><br>
        <a href="#">다섯여섯일곱여덟</a>
    `
}



// QnA
function sendMessage() {
    let userInput = document.getElementById("userInput")
    let sayText = document.getElementById("sayText")

    if (userInput.value == "") {
        sayText.innerText = "무엇이든 물어봐 주세요!"
    } else {
        sayText.innerText = "좋은 질문이에요! 잠시만 기다려 주세요."
    }

    userInput.value = ""
}