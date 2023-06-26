
// as document fully loaded
document.addEventListener("DOMContentLoaded", function() {
    // take all offcanvas buttons
    document.querySelectorAll(".offcanvas_btn").forEach(btn => {
        // add event lestener for each
        btn.addEventListener("click", function() {
            
            // access data attributes and store them
            let symbol = this.dataset.symbol,
                amount = this.dataset.amount;

            console.log(symbol, amount)

            // select offcanvas elements
            // insert symbol to offcanvas heading
            document.querySelector("#offcanvas_title").innerHTML = symbol;
            document.querySelector("#symbol").value = symbol;



        });
    });





});